import json
import logging
import os
import re
from collections import Counter
from difflib import SequenceMatcher
from typing import Any, Optional

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.services.ocr_service import OCRService, get_ocr_service
from app.services.vision_service import VisionService, get_vision_service

logger = logging.getLogger(__name__)


# ── Standalone sequential grouping functions ─────────────────

def detect_name_in_text(text: str) -> Optional[str]:
    """Detect student name in OCR text.

    Patterns:
    - "Name: John Doe"
    - "Nombre: Juan P\u00e9rez"
    - "Student: Mar\u00eda Garc\u00eda"
    """
    # Pattern 1: Label-prefixed names (most reliable)
    label_pattern = r"(?:Name|Nombre|Student|Alumno|Estudiante)\s*:\s*([A-Z\u00c1-\u00da][a-z\u00e1\u00e9\u00ed\u00f3\u00fa\u00f1]+(?:\s+[A-Z\u00c1-\u00da][a-z\u00e1\u00e9\u00ed\u00f3\u00fa\u00f1]+)+)"

    match = re.search(label_pattern, text, re.MULTILINE | re.IGNORECASE)
    if match:
        name = match.group(1).strip()
        if len(name.split()) >= 2 and len(name) >= 6:
            return name

    return None


DETECT_NAME_VISION_PROMPT_STANDALONE = """\
You are an expert at reading student exams. Look at this exam page and find the student's name.

Return a JSON object with exactly one key:
{"student_name": "the student's full name" or null if no name is visible}

Return ONLY valid JSON, no markdown fences, no explanation."""


async def _detect_name_with_vision(image_path: str, vision_service: Any) -> Optional[str]:
    """Use Claude Vision to detect the student name from an exam photo."""
    try:
        raw = await vision_service._call_vision(
            image_path=image_path,
            system_prompt=DETECT_NAME_VISION_PROMPT_STANDALONE,
            user_text="Find the student's name on this exam page.",
        )
        # Parse JSON
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned[cleaned.index("\n") + 1:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:cleaned.rfind("```")]
        import json as _json
        result = _json.loads(cleaned.strip())
        name = result.get("student_name")
        if name and isinstance(name, str) and len(name.strip()) >= 2:
            logger.info("\u2502   Vision detected name: '%s'", name.strip())
            return name.strip()
        logger.info("\u2502   Vision did not find a name")
        return None
    except Exception as exc:
        logger.error("\u2502   Vision name detection failed: %s", exc)
        return None


def _names_are_similar(a: str, b: str, threshold: float = 0.75) -> bool:
    """Check if two names are similar enough to be the same student."""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio() >= threshold


async def group_photos_by_student_sequential(
    photo_urls: list[str],
    ocr_service: OCRService,
    storage_service: Any,
    vision_service: Any = None,
) -> list[dict]:
    """Group photos SEQUENTIALLY (like a scanner app).

    RULE:
    - Photo WITH name SIMILAR to current student -> CONTINUES same student
    - Photo WITH name DIFFERENT from current student -> NEW student
    - Photo WITHOUT name -> CONTINUES previous student

    Uses OCR first, then Vision API (Claude) as fallback for name detection.
    If both fail, continues the previous student or creates Unknown_Student.

    Returns:
        [
            {"student_name": "Camila...", "photo_urls": ["url1", "url2"], "page_count": 2},
            {"student_name": "Juan...", "photo_urls": ["url3", "url4"], "page_count": 2}
        ]
    """
    groups: list[dict] = []
    current_student: Optional[str] = None
    current_photos: list[str] = []

    logger.info("\u2554\u2550\u2550\u2550 SEQUENTIAL GROUPING START: %d photos \u2550\u2550\u2550\u2557", len(photo_urls))

    for idx, photo_url in enumerate(photo_urls, 1):
        temp_path: Optional[str] = None
        try:
            # Download image to temp file
            temp_path = await storage_service.download_to_temp(photo_url)
            logger.info("\u2502 Photo %d/%d: downloaded %s", idx, len(photo_urls), photo_url[:60])

            detected_name: Optional[str] = None

            # Step 1: Try OCR
            try:
                ocr_text = await ocr_service.extract_text(temp_path)
                detected_name = detect_name_in_text(ocr_text)
                if detected_name:
                    logger.info("\u2502   OCR detected name: '%s'", detected_name)
                else:
                    logger.info("\u2502   OCR: no name pattern found in text (%d chars)", len(ocr_text))
            except Exception as ocr_err:
                logger.warning("\u2502   OCR failed (non-fatal): %s", ocr_err)

            # Step 2: Vision fallback if OCR didn't find name
            if not detected_name and vision_service:
                logger.info("\u2502   Trying Vision API for name detection...")
                detected_name = await _detect_name_with_vision(temp_path, vision_service)

            # Step 3: Log result
            logger.info(
                "\u2502 Photo %d/%d result: name=%s",
                idx, len(photo_urls),
                "\u2713 " + detected_name if detected_name else "\u2717 (no name)",
            )

            if detected_name:
                # Check if this name is SIMILAR to the current student (same person, different reading)
                if current_student and _names_are_similar(detected_name, current_student):
                    # SAME student — just add the photo
                    current_photos.append(photo_url)
                    logger.info(
                        "\u2502   \u2248 Name '%s' matches current '%s' (fuzzy) — continuing (%d pages)",
                        detected_name, current_student, len(current_photos),
                    )
                else:
                    # DIFFERENT student — save previous if exists
                    if current_student and current_photos:
                        groups.append({
                            "student_name": current_student,
                            "photo_urls": current_photos.copy(),
                            "page_count": len(current_photos),
                        })
                        logger.info(
                            "\u2502   \u2713 Completed '%s': %d page(s)",
                            current_student, len(current_photos),
                        )

                    # Start new student
                    current_student = detected_name
                    current_photos = [photo_url]
                    logger.info("\u2502   \u2192 NEW student: '%s'", current_student)

            else:
                # No name -> continues previous
                if current_student:
                    current_photos.append(photo_url)
                    logger.info(
                        "\u2502   + Added to '%s' (now %d pages)",
                        current_student, len(current_photos),
                    )
                else:
                    # First photo with no name
                    logger.warning("\u2502   \u26a0 First photo has no name — creating Unknown_Student")
                    current_student = f"Unknown_Student_{idx}"
                    current_photos = [photo_url]

        except Exception as e:
            logger.error("\u2502   \u2717 Error processing photo %d: %s", idx, e)
            # Even on error, don't lose the photo — add it to current group
            if current_student:
                current_photos.append(photo_url)
            else:
                current_student = f"Unknown_Student_{idx}"
                current_photos = [photo_url]
        finally:
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)

    # Save last student
    if current_student and current_photos:
        groups.append({
            "student_name": current_student,
            "photo_urls": current_photos.copy(),
            "page_count": len(current_photos),
        })
        logger.info(
            "\u2502   \u2713 FINAL student '%s': %d page(s)",
            current_student, len(current_photos),
        )

    # Summary
    logger.info("\u2560\u2550\u2550\u2550 GROUPING COMPLETE: %d students \u2550\u2550\u2550\u2563", len(groups))
    for i, g in enumerate(groups, 1):
        logger.info("\u2502 %d. %s: %d page(s)", i, g["student_name"], g["page_count"])
    logger.info("\u255a" + "\u2550" * 51 + "\u255d")

    return groups


async def group_photos_by_student(
    photo_urls: list[str],
) -> list[dict]:
    """Wrapper that uses sequential grouping with default services."""
    from app.services.storage_service import get_storage_service

    ocr = get_ocr_service()
    storage = get_storage_service()

    return await group_photos_by_student_sequential(
        photo_urls,
        ocr,
        storage,
    )


# ── Prompts ──────────────────────────────────────────────────

DETECT_NAME_VISION_PROMPT = """\
You are an expert at reading student exams. Look at this exam page and find the student's name.

Return a JSON object with exactly one key:
{{"student_name": "the student's full name" or null if no name is visible}}

Return ONLY valid JSON, no markdown fences, no explanation."""

MERGE_ANSWERS_PROMPT = """\
You are an expert exam grader assistant. You have multiple pages of a single student's exam.
The exam template structure is:
{template_json}

OCR text extracted from each page:
{pages_text}

Your job: combine all the answers from all pages into a single answer set following the template structure.

Return a JSON object mapping question numbers to the student's answer:
{{
  "1": "B",
  "2": "A",
  "3": "The student's written answer here…"
}}

Rules:
- For multiple choice, return the letter (A, B, C, D).
- For true/false, return "True" or "False".
- For written answers, transcribe exactly what the student wrote.
- If an answer is blank or not found, use null.
- If the same question appears on multiple pages, use the most complete answer.
- Return ONLY valid JSON, no markdown fences, no explanation."""


class GroupingService:
    """Service for grouping exam photos by student and merging multi-page answers."""

    def __init__(
        self,
        ocr_service: Optional[OCRService] = None,
        vision_service: Optional[VisionService] = None,
    ) -> None:
        self._ocr = ocr_service or get_ocr_service()
        self._vision = vision_service or get_vision_service()
        logger.info("GroupingService initialized")

    # ── Helpers ──────────────────────────────────────────────

    @staticmethod
    def _normalize_name(name: str) -> str:
        """Normalize a student name for comparison."""
        return " ".join(name.strip().split()).title()

    @staticmethod
    def _names_are_similar(a: str, b: str, threshold: float = 0.80) -> bool:
        """Check if two names are similar enough to be the same person."""
        return SequenceMatcher(None, a.lower(), b.lower()).ratio() >= threshold

    @staticmethod
    def _parse_json_response(text: str) -> dict[str, Any]:
        """Parse JSON from an AI response, stripping markdown fences if present."""
        cleaned = text.strip()
        if cleaned.startswith("```"):
            first_newline = cleaned.index("\n")
            cleaned = cleaned[first_newline + 1 :]
        if cleaned.endswith("```"):
            cleaned = cleaned[: cleaned.rfind("```")]
        cleaned = cleaned.strip()
        return json.loads(cleaned)

    # ── Vision fallback for name detection ───────────────────

    async def _detect_name_with_vision(self, image_path: str) -> Optional[str]:
        """Use Claude Vision to detect the student name from an exam photo."""
        try:
            raw = await self._vision._call_vision(
                image_path=image_path,
                system_prompt=DETECT_NAME_VISION_PROMPT,
                user_text="Find the student's name on this exam page.",
            )
            result = self._parse_json_response(raw)
            name = result.get("student_name")
            if name and isinstance(name, str) and len(name.strip()) >= 2:
                logger.info("Vision detected student name: %s", name)
                return name.strip()
            logger.warning("Vision did not find a student name in %s", image_path)
            return None
        except Exception as exc:
            logger.error("Vision name detection failed for %s: %s", image_path, exc)
            return None

    # ── 1. Group photos by student ───────────────────────────

    async def group_photos_by_student(
        self, photo_paths: list[str]
    ) -> dict[str, list[str]]:
        """Process each photo, detect student name, and group by student.

        Pipeline per photo:
        1. OCR extract_text → detect_name
        2. If OCR fails → Vision (Claude) fallback
        3. If still no name → assume continuation of previous student

        Returns: {"Student Name": ["photo1.jpg", "photo2.jpg"], ...}
        """
        grouped: dict[str, list[str]] = {}
        last_name: Optional[str] = None

        logger.info("Grouping %d photos by student…", len(photo_paths))

        for i, path in enumerate(photo_paths):
            logger.debug("Processing photo %d/%d: %s", i + 1, len(photo_paths), path)

            name: Optional[str] = None

            # Step 1: Try OCR-based name detection
            try:
                ocr_text = await self._ocr.extract_text(path)
                name = await self._ocr.detect_name(ocr_text)
                if name:
                    logger.debug("OCR detected name '%s' in %s", name, path)
            except Exception as exc:
                logger.warning("OCR failed for %s: %s", path, exc)

            # Step 2: Vision fallback if OCR didn't find a name
            if not name:
                logger.debug("OCR name detection failed for %s, trying Vision…", path)
                name = await self._detect_name_with_vision(path)

            # Step 3: No name found → continuation of previous student
            if not name:
                if last_name:
                    name = last_name
                    logger.info(
                        "No name in %s — assuming continuation of '%s'", path, name
                    )
                else:
                    name = "Desconocido"
                    logger.warning(
                        "No name detected and no previous student for %s", path
                    )

            # Normalize and group
            normalized = self._normalize_name(name)

            # Check for similar existing names (fuzzy dedup)
            matched_key: Optional[str] = None
            for existing_name in grouped:
                if self._names_are_similar(normalized, existing_name):
                    matched_key = existing_name
                    break

            if matched_key:
                grouped[matched_key].append(path)
                last_name = matched_key
            else:
                grouped[normalized] = [path]
                last_name = normalized

        for name, photos in grouped.items():
            logger.info("Student '%s': %d page(s) detected", name, len(photos))
        logger.info(
            "Grouped %d photos into %d students: %s",
            len(photo_paths),
            len(grouped),
            list(grouped.keys()),
        )
        return grouped

    # ── 2. Merge student pages ───────────────────────────────

    async def merge_student_pages(
        self,
        grouped_photos: dict[str, list[str]],
        template: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        """For each student, extract and merge answers from all their pages.

        Processes each page individually with VisionService.extract_student_answers
        (proven working), then merges results. Later pages fill in answers that
        were null/missing on earlier pages but never overwrite non-null values.

        Returns: {"Student Name": {"1": {"value": "B", ...}, "2": ...}, ...}
        """
        results: dict[str, dict[str, Any]] = {}

        logger.info(
            "Merging pages for %d students…", len(grouped_photos)
        )

        for student_name, photos in grouped_photos.items():
            logger.info(
                "Student '%s': %d page(s) — extracting answers per page",
                student_name, len(photos),
            )

            try:
                merged_answers: dict[str, Any] = {}

                for idx, photo_path in enumerate(photos):
                    logger.info(
                        "Student '%s' page %d/%d: %s",
                        student_name, idx + 1, len(photos), photo_path,
                    )

                    try:
                        extraction = await self._vision.extract_student_answers(
                            image_path=photo_path, template=template
                        )
                        page_answers = extraction.get("answers", {})
                    except Exception as exc:
                        logger.error(
                            "Vision extraction failed for '%s' page %d: %s",
                            student_name, idx + 1, exc,
                        )
                        page_answers = {}

                    page_count = len(page_answers)
                    non_null = sum(
                        1 for a in page_answers.values()
                        if a is not None
                        and not (isinstance(a, dict) and a.get("value") is None)
                    )
                    logger.info(
                        "Student '%s' page %d: %d answers extracted (%d non-null)",
                        student_name, idx + 1, page_count, non_null,
                    )

                    # Merge: new answers fill gaps, never overwrite existing non-null
                    for q_id, answer in page_answers.items():
                        existing = merged_answers.get(q_id)
                        existing_is_null = (
                            existing is None
                            or (isinstance(existing, dict) and existing.get("value") is None)
                        )
                        if existing_is_null:
                            merged_answers[q_id] = answer

                results[student_name] = merged_answers

                total = len(merged_answers)
                non_null_total = sum(
                    1 for a in merged_answers.values()
                    if a is not None
                    and not (isinstance(a, dict) and a.get("value") is None)
                )
                logger.info(
                    "Student '%s' MERGED: %d total answers (%d non-null) from %d page(s)",
                    student_name, total, non_null_total, len(photos),
                )

            except Exception as exc:
                logger.error(
                    "Failed to merge pages for '%s': %s", student_name, exc
                )
                results[student_name] = {}

        return results

    # ── 3. Validate grouping ─────────────────────────────────

    def validate_grouping(
        self, grouped_photos: dict[str, list[str]]
    ) -> list[dict[str, str]]:
        """Detect potential problems in photo grouping.

        Returns a list of warning dicts:
        [{"type": "...", "message": "...", "suggestion": "..."}, ...]
        """
        warnings: list[dict[str, str]] = []

        all_names = list(grouped_photos.keys())

        # Check for "Desconocido" (unknown student)
        if "Desconocido" in grouped_photos:
            count = len(grouped_photos["Desconocido"])
            warnings.append({
                "type": "unidentified",
                "message": f"{count} foto(s) sin nombre de estudiante detectado.",
                "suggestion": "Revise manualmente las fotos y asigne un nombre.",
            })

        # Check for similar names (possible duplicates)
        for i, name_a in enumerate(all_names):
            for name_b in all_names[i + 1 :]:
                if name_a == "Desconocido" or name_b == "Desconocido":
                    continue
                similarity = SequenceMatcher(None, name_a.lower(), name_b.lower()).ratio()
                if 0.65 <= similarity < 0.80:
                    warnings.append({
                        "type": "ambiguous_name",
                        "message": (
                            f"Nombres similares detectados: '{name_a}' y '{name_b}' "
                            f"(similitud: {similarity:.0%})."
                        ),
                        "suggestion": (
                            f"Verifique si '{name_a}' y '{name_b}' son el mismo estudiante."
                        ),
                    })

        # Check for students with unusually many or few pages
        page_counts = [len(photos) for photos in grouped_photos.values()]
        if page_counts:
            avg_pages = sum(page_counts) / len(page_counts)
            for name, photos in grouped_photos.items():
                count = len(photos)
                if count == 1 and avg_pages > 2.0:
                    warnings.append({
                        "type": "few_pages",
                        "message": (
                            f"'{name}' tiene solo {count} foto(s) "
                            f"(promedio del grupo: {avg_pages:.1f})."
                        ),
                        "suggestion": (
                            "Podría faltar una página o estar agrupada con otro estudiante."
                        ),
                    })
                elif count > avg_pages * 2 and avg_pages > 0:
                    warnings.append({
                        "type": "many_pages",
                        "message": (
                            f"'{name}' tiene {count} foto(s), "
                            f"más del doble del promedio ({avg_pages:.1f})."
                        ),
                        "suggestion": (
                            "Podría haber fotos de otro estudiante mezcladas."
                        ),
                    })

        # Check for empty groups (shouldn't happen but defensive)
        for name, photos in grouped_photos.items():
            if not photos:
                warnings.append({
                    "type": "empty_group",
                    "message": f"Grupo '{name}' no tiene fotos asignadas.",
                    "suggestion": "Elimine el grupo vacío.",
                })

        logger.info("Validation found %d warnings", len(warnings))
        return warnings


# ── Module-level singleton ───────────────────────────────────

_grouping_service: Optional[GroupingService] = None


def get_grouping_service() -> GroupingService:
    global _grouping_service
    if _grouping_service is None:
        _grouping_service = GroupingService()
    return _grouping_service
