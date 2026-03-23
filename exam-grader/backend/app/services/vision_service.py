import base64
import json
import logging
from pathlib import Path
from typing import Any, Optional

import anthropic
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# ── Prompts ──────────────────────────────────────────────────

STRUCTURE_TEMPLATE_PROMPT = """\
You are an expert exam analyzer. You receive a photo of a **clean exam template** \
(no student answers filled in).

Analyze the image and return a JSON object with the exam structure. Follow this exact schema:

{
  "name": "string — exam title if visible, otherwise 'Untitled Exam'",
  "subject": "string — subject if detectable, otherwise 'General'",
  "max_score": number,
  "sections": [
    {
      "name": "string — section title, e.g. 'LISTENING'",
      "total_points": number,
      "parts": [
        {
          "name": "string — part title, e.g. 'Multiple Choice'",
          "questions": ["1", "2", "3"],
          "type": "multiple_choice | true_false | fill_blank | short_answer | long_answer | matching",
          "options": ["A", "B", "C", "D"] or null,
          "points_each": number
        }
      ]
    }
  ]
}

Rules:
- Number questions sequentially across the entire exam (1, 2, 3… not restarting per section).
- Detect question types from visual cues (circles/bubbles = multiple_choice, lines = fill_blank, etc.).
- If point values are not visible, distribute evenly within each section.
- Return ONLY valid JSON, no markdown fences, no explanation.
"""

EXTRACT_ANSWERS_PROMPT = """\
You are an expert exam grader assistant. You receive:
1. A photo of a **student's completed exam**.
2. The exam template structure (JSON).

Your job: extract every answer the student wrote or marked, and rate your confidence for each.

Template structure:
{template_json}

Return a JSON object where each answer is an object with confidence metadata:

{{
  "student_name": "string or null if not found",
  "answers": {{
    "1": {{"value": "B", "confidence": "high"}},
    "2": {{"value": "A", "confidence": "high"}},
    "3": {{"value": "The student's written answer…", "confidence": "medium", "reason": "Some words are illegible"}},
    "5": {{"value": "C", "confidence": "low", "alternatives": ["A", "C"], "reason": "Handwriting unclear, could be A or C"}}
  }}
}}

Confidence levels:
- "high"  : >90% certain — answer is clearly legible/marked
- "medium": 70–90% certain — mostly legible but minor ambiguity
- "low"   : <70% certain — handwriting unclear, erased, ambiguous mark

Rules:
- For multiple choice, value is the letter (A, B, C, D).
- For true/false, value is "True" or "False".
- For written answers, transcribe exactly what the student wrote.
- If an answer is blank or missing, use {{"value": null, "confidence": "high"}}.
- Only include "alternatives" and "reason" when confidence is "medium" or "low".
- NEVER guess on low confidence answers — surface them for teacher review instead.
- Return ONLY valid JSON, no markdown fences, no explanation.
"""

STRUCTURE_SEPARATE_PROMPT_BASE = """\
You are an expert exam analyzer. You receive image(s) of an exam answer sheet.

{booklet_note}

CRITICAL: Examine ALL images carefully. The exam may span MULTIPLE PAGES.
Look for section headers like "LISTENING", "WRITING", "READING", etc. across ALL pages.
Also look for a SCORE SUMMARY table (often at the bottom of the last page) which lists all sections and their point values.

{booklet_instruction}

Return a JSON object with the COMPLETE exam structure. Follow this exact schema:

{{
  "name": "string — exam title if visible, otherwise 'Untitled Exam'",
  "subject": "string — subject if detectable, otherwise 'General'",
  "max_score": number — THIS IS THE SUM of all section total_points,
  "sections": [
    {{
      "name": "string — section title, e.g. 'LISTENING'",
      "total_points": number — IMPORTANT: calculate as (number_of_questions × points_each). Example: '50 x 0.5' means 50 questions at 0.5 points each = 25 total points, NOT 50,
      "parts": [
        {{
          "name": "string — part title, e.g. 'Part A - Multiple Choice'",
          "questions": ["1", "2", "3"],
          "type": "multiple_choice | true_false | fill_blank | short_answer | long_answer | matching",
          "options": ["A", "B", "C", "D"] or null,
          "points_each": number
        }}
      ]
    }}
  ]
}}

Rules:
- MUST include ALL sections from ALL pages. Do NOT stop at page 1.
- Number questions sequentially across the ENTIRE exam (1, 2, 3… continuing across sections, not restarting per section).
- total_points for a section = sum of (questions_count × points_each) for all parts in that section.
- If the exam says "25 pts (50 x 0.5)", the section total_points is 25 (not 50). The 50 is the question count, 0.5 is points_each.
- If the exam says "25 pts (20 x 1.25)", the section total_points is 25. The 20 is question count, 1.25 is points_each.
- max_score = sum of all section total_points.
- Detect answer types from visual cues (bubbles/circles = multiple_choice, T/F = true_false, lines = fill_blank, etc.).
- Return ONLY valid JSON, no markdown fences, no explanation."""


class VisionService:
    """Anthropic Claude Vision service for exam analysis."""

    MODEL = "claude-sonnet-4-20250514"
    MAX_TOKENS = 8192

    def __init__(self) -> None:
        settings = get_settings()
        self._client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    # ── Helpers ──────────────────────────────────────────────

    @staticmethod
    def _encode_image(image_path: str) -> tuple[str, str]:
        """Read an image file and return (base64_data, media_type)."""
        path = Path(image_path)
        if not path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")

        suffix = path.suffix.lower()
        media_map: dict[str, str] = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }
        media_type = media_map.get(suffix)
        if media_type is None:
            raise ValueError(f"Unsupported image format: {suffix}")

        data = path.read_bytes()
        if len(data) > 20 * 1024 * 1024:
            raise ValueError(f"Image too large ({len(data) / 1024 / 1024:.1f} MB). Max 20 MB.")

        return base64.standard_b64encode(data).decode("ascii"), media_type

    @staticmethod
    def _parse_json_response(text: str) -> dict[str, Any]:
        """Parse JSON from Claude's response, stripping markdown fences if present."""
        cleaned = text.strip()
        if cleaned.startswith("```"):
            first_newline = cleaned.index("\n")
            cleaned = cleaned[first_newline + 1 :]
        if cleaned.endswith("```"):
            cleaned = cleaned[: cleaned.rfind("```")]
        cleaned = cleaned.strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as exc:
            logger.error("Failed to parse Claude JSON response: %s", exc)
            logger.debug("Raw response:\n%s", text)
            raise ValueError(f"Claude returned invalid JSON: {exc}") from exc

    # ── API calls with retry ─────────────────────────────────

    @retry(
        retry=retry_if_exception_type(
            (anthropic.RateLimitError, anthropic.APIStatusError, anthropic.APIConnectionError)
        ),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        stop=stop_after_attempt(5),
        reraise=True,
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    async def _call_vision(
        self,
        image_path: str,
        system_prompt: str,
        user_text: Optional[str] = None,
    ) -> str:
        """Send an image + prompt to Claude and return the text response."""
        b64_data, media_type = self._encode_image(image_path)

        content: list[dict[str, Any]] = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": b64_data,
                },
            },
        ]
        if user_text:
            content.append({"type": "text", "text": user_text})

        logger.debug("Calling Claude Vision (%s) for %s", self.MODEL, image_path)

        response = await self._client.messages.create(
            model=self.MODEL,
            max_tokens=self.MAX_TOKENS,
            messages=[{"role": "user", "content": content}],
            system=system_prompt,
        )

        result_text = response.content[0].text
        logger.info(
            "Claude response: %d chars, stop_reason=%s, usage=%s",
            len(result_text),
            response.stop_reason,
            response.usage,
        )
        return result_text

    @retry(
        retry=retry_if_exception_type(
            (anthropic.RateLimitError, anthropic.APIStatusError, anthropic.APIConnectionError)
        ),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        stop=stop_after_attempt(5),
        reraise=True,
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    async def _call_vision_multi(
        self,
        image_paths: list[str],
        system_prompt: str,
        user_text: Optional[str] = None,
    ) -> str:
        """Send multiple images + prompt to Claude and return the text response."""
        content: list[dict[str, Any]] = []
        for path in image_paths:
            b64_data, media_type = self._encode_image(path)
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": b64_data,
                },
            })
        if user_text:
            content.append({"type": "text", "text": user_text})

        logger.debug("Calling Claude Vision (%s) with %d images", self.MODEL, len(image_paths))

        response = await self._client.messages.create(
            model=self.MODEL,
            max_tokens=self.MAX_TOKENS,
            messages=[{"role": "user", "content": content}],
            system=system_prompt,
        )

        result_text = response.content[0].text
        logger.info(
            "Claude multi-image response: %d chars, stop_reason=%s",
            len(result_text),
            response.stop_reason,
        )
        return result_text

    # ── Public methods ───────────────────────────────────────

    async def structure_exam_template(self, image_path: str) -> dict[str, Any]:
        """Analyze a clean exam photo and return its structure as a dict.

        Returns a dict matching the exam_templates.structure_json schema.
        """
        logger.info("Structuring exam template from: %s", image_path)

        raw = await self._call_vision(
            image_path=image_path,
            system_prompt=STRUCTURE_TEMPLATE_PROMPT,
        )
        structure = self._parse_json_response(raw)

        # Basic validation
        if "sections" not in structure:
            raise ValueError("Claude response missing 'sections' key")

        logger.info(
            "Template structured: %d sections, max_score=%s",
            len(structure.get("sections", [])),
            structure.get("max_score"),
        )
        return structure

    async def structure_exam_template_separate(
        self,
        answer_sheet_paths: list[str] | None = None,
        booklet_paths: list[str] | None = None,
        # Legacy single-path args (backward compat)
        answer_sheet_path: Optional[str] = None,
        question_book_path: Optional[str] = None,
    ) -> dict[str, Any]:
        """Analyze answer sheet + optional question booklet and return exam structure.

        Accepts lists of image paths (one per page) for multi-page PDFs.
        """
        # Handle legacy single-path callers
        if answer_sheet_paths is None:
            answer_sheet_paths = [answer_sheet_path] if answer_sheet_path else []
        if booklet_paths is None:
            booklet_paths = [question_book_path] if question_book_path else []

        has_booklet = len(booklet_paths) > 0
        total_images = len(answer_sheet_paths) + len(booklet_paths)

        logger.info(
            "╔═══ STRUCTURE SEPARATE MODE ═══╗\n"
            "║ Answer sheet pages: %d\n"
            "║ Booklet pages:      %d\n"
            "║ Total images:       %d\n"
            "╚═══════════════════════════════╝",
            len(answer_sheet_paths), len(booklet_paths), total_images,
        )

        # Build image list with descriptive labels
        image_paths: list[str] = []
        image_labels: list[str] = []

        for i, path in enumerate(answer_sheet_paths, 1):
            image_paths.append(path)
            label = f"Answer Sheet Page {i}" if len(answer_sheet_paths) > 1 else "Answer Sheet"
            image_labels.append(label)

        for i, path in enumerate(booklet_paths, 1):
            image_paths.append(path)
            label = f"Question Booklet Page {i}" if len(booklet_paths) > 1 else "Question Booklet"
            image_labels.append(label)

        if has_booklet:
            labels_desc = ", ".join(
                f"Image {i+1} = {label}" for i, label in enumerate(image_labels)
            )
            booklet_note = (
                f"You are receiving {total_images} images:\n{labels_desc}\n\n"
                "IMPORTANT: The exam spans MULTIPLE PAGES. You MUST examine EVERY image.\n"
                "Each image may contain different sections (e.g., LISTENING on page 1, "
                "GRAMMAR on page 2, READING on page 3). Include ALL sections from ALL pages."
            )
            booklet_instruction = (
                f"Analyze ALL {total_images} images together. Extract ALL sections, parts, "
                "and questions from EVERY page. Do NOT stop after the first few images. "
                "VERIFY: your output must include sections from the LAST image too."
            )
        else:
            booklet_note = (
                "(Only answer sheet image(s) provided — structure based on these only. "
                "If the exam has more pages, some sections may be missing.)"
            )
            booklet_instruction = ""

        system_prompt = STRUCTURE_SEPARATE_PROMPT_BASE.format(
            booklet_note=booklet_note,
            booklet_instruction=booklet_instruction,
        )

        logger.info("Sending %d images to Claude Vision for structure extraction", len(image_paths))

        raw = await self._call_vision_multi(
            image_paths=image_paths,
            system_prompt=system_prompt,
        )
        structure = self._parse_json_response(raw)

        if "sections" not in structure:
            raise ValueError("Claude response missing 'sections' key")

        # Log detected sections
        sections = structure.get("sections", [])
        logger.info(
            "Separate template structured: %d sections, max_score=%s",
            len(sections), structure.get("max_score"),
        )
        for sec in sections:
            q_count = sum(len(p.get("questions", [])) for p in sec.get("parts", []))
            logger.info(
                "  Section: '%s' | %s pts | %d questions",
                sec.get("name"), sec.get("total_points"), q_count,
            )

        return structure

    async def extract_student_answers(
        self,
        image_path: str,
        template: dict[str, Any],
    ) -> dict[str, Any]:
        """Extract student answers from a completed exam photo.

        Args:
            image_path: Path to the student's exam image.
            template: The exam structure dict (from structure_exam_template).

        Returns a dict with keys: student_name, answers, confidence_flags.
        """
        logger.info("Extracting student answers from: %s", image_path)

        template_json = json.dumps(template, ensure_ascii=False, indent=2)
        prompt = EXTRACT_ANSWERS_PROMPT.format(template_json=template_json)

        raw = await self._call_vision(
            image_path=image_path,
            system_prompt=prompt,
            user_text="Extract all answers from this completed exam.",
        )
        result = self._parse_json_response(raw)

        # Basic validation
        if "answers" not in result:
            raise ValueError("Claude response missing 'answers' key")

        answers = result.get("answers", {})
        answer_count = len(answers)
        low_confidence_count = sum(
            1 for a in answers.values()
            if isinstance(a, dict) and a.get("confidence") == "low"
        )
        logger.info(
            "Extracted %d answers (%d low-confidence) for student: %s",
            answer_count,
            low_confidence_count,
            result.get("student_name", "unknown"),
        )
        return result

    async def extract_student_answers_multi_page(
        self,
        image_paths: list[str],
        template: dict[str, Any],
    ) -> dict[str, Any]:
        """Extract student answers from multiple exam page images in a single call.

        NOTE: Currently unused — merge_student_pages uses per-page loop instead.
        Kept for future optimization once multi-image prompt is refined.

        Args:
            image_paths: List of paths to the student's exam page images.
            template: The exam structure dict (from structure_exam_template).

        Returns a dict with keys: student_name, answers.
        """
        if len(image_paths) == 1:
            return await self.extract_student_answers(image_paths[0], template)

        logger.info(
            "=== MULTI-PAGE EXTRACT START === pages=%d paths=%s",
            len(image_paths), image_paths,
        )

        template_json = json.dumps(template, ensure_ascii=False, indent=2)
        prompt = EXTRACT_ANSWERS_PROMPT.format(template_json=template_json)
        logger.debug("Multi-page system prompt length: %d chars", len(prompt))

        page_labels = ", ".join(f"Image {i+1} = Page {i+1}" for i in range(len(image_paths)))
        user_text = (
            f"This student's exam has {len(image_paths)} pages ({page_labels}). "
            "Extract ALL answers from ALL pages. Do NOT skip any page."
        )
        logger.debug("Multi-page user_text: %s", user_text)

        raw = await self._call_vision_multi(
            image_paths=image_paths,
            system_prompt=prompt,
            user_text=user_text,
        )
        logger.info(
            "Multi-page raw response length: %d chars, preview: %.500s",
            len(raw), raw,
        )

        result = self._parse_json_response(raw)

        if "answers" not in result:
            logger.error("Multi-page response missing 'answers' key. Keys: %s", list(result.keys()))
            raise ValueError("Claude response missing 'answers' key")

        answers = result.get("answers", {})
        answer_count = len(answers)
        low_confidence_count = sum(
            1 for a in answers.values()
            if isinstance(a, dict) and a.get("confidence") == "low"
        )
        logger.info(
            "=== MULTI-PAGE EXTRACT END === %d answers (%d low-confidence) from %d pages, student: %s, keys: %s",
            answer_count,
            low_confidence_count,
            len(image_paths),
            result.get("student_name", "unknown"),
            list(answers.keys())[:15],
        )
        return result


# ── Module-level singleton ───────────────────────────────────

_vision_service: Optional[VisionService] = None


def get_vision_service() -> VisionService:
    global _vision_service
    if _vision_service is None:
        _vision_service = VisionService()
    return _vision_service