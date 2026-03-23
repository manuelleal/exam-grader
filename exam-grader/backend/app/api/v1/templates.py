import logging
import os
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status

from app.core.database import get_supabase_client
from app.core.security import get_current_teacher_id
from app.schemas.template import (
    AnswerKeyUpdate,
    StructureUpdate,
    TemplateCreate,
    TemplateExtractResponse,
    TemplateListResponse,
    TemplateResponse,
    TemplateUploadResponse,
)
from app.services.storage_service import get_storage_service
from app.services.vision_service import get_vision_service

logger = logging.getLogger(__name__)

router = APIRouter()

TeacherId = Annotated[str, Depends(get_current_teacher_id)]


# ── Helpers ──────────────────────────────────────────────────

def _row_to_response(row: dict[str, Any]) -> TemplateResponse:
    """Convert a Supabase row dict to a TemplateResponse."""
    return TemplateResponse(
        id=row["id"],
        teacher_id=row["teacher_id"],
        name=row["name"],
        subject=row["subject"],
        mode=row["mode"],
        max_score=float(row["max_score"]),
        template_image_url=row.get("template_image_url"),
        question_book_url=row.get("question_book_url"),
        answer_sheet_template_url=row.get("answer_sheet_template_url"),
        structure_json=row.get("structure_json"),
        answer_key_json=row.get("answer_key_json"),
        answer_key_method=row.get("answer_key_method"),
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )


def _normalize_structure_points(structure: dict[str, Any]) -> dict[str, Any]:
    """Normalize points_each in each section so calculated sum == declared total_points.

    The Vision AI sometimes assigns wrong points_each but correct total_points.
    This function redistributes points_each proportionally so the math adds up.
    """
    recalc_max = 0.0
    for section in structure.get("sections", []):
        declared = float(section.get("total_points", 0))
        parts = section.get("parts", [])
        total_questions = sum(len(p.get("questions", [])) for p in parts)

        if total_questions == 0 or declared <= 0:
            continue

        # Calculate what the AI gave
        calculated = sum(
            len(p.get("questions", [])) * float(p.get("points_each", 1))
            for p in parts
        )

        if abs(calculated - declared) > 0.01:
            # Points don't match — redistribute evenly based on declared total
            uniform_ppe = round(declared / total_questions, 4)
            logger.warning(
                "Section '%s': calculated=%.1f != declared=%.1f. "
                "Normalizing %d questions to %.4f pts each.",
                section.get("name"), calculated, declared,
                total_questions, uniform_ppe,
            )
            for part in parts:
                part["points_each"] = uniform_ppe

        recalc_max += declared

    # Also fix max_score to match sum of declared section totals
    if recalc_max > 0:
        structure["max_score"] = recalc_max

    return structure


def _url_is_pdf(url: str) -> bool:
    """Check if a URL points to a PDF file."""
    from urllib.parse import urlparse
    path = urlparse(url).path.lower()
    return path.rstrip("/").endswith(".pdf")


def _parse_url_field(url_field: str | None) -> list[str]:
    """Parse a template URL field that may be a single URL or JSON array of URLs.

    Returns a list of individual image URLs.
    """
    if not url_field:
        return []
    url_field = url_field.strip()
    if url_field.startswith("["):
        # JSON array of URLs (from multi-page PDF upload)
        import json
        try:
            urls = json.loads(url_field)
            if isinstance(urls, list):
                return [u for u in urls if isinstance(u, str)]
        except (json.JSONDecodeError, TypeError):
            pass
    # Single URL string
    return [url_field]


async def _get_template_or_404(
    template_id: str,
    teacher_id: str,
) -> dict[str, Any]:
    """Fetch a template ensuring it belongs to the teacher."""
    sb = await get_supabase_client()
    result = (
        await sb.table("exam_templates")
        .select("*")
        .eq("id", template_id)
        .eq("teacher_id", teacher_id)
        .limit(1)
        .execute()
    )
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template '{template_id}' not found",
        )
    return result.data[0]


# ── POST /templates ──────────────────────────────────────────

@router.post(
    "",
    response_model=TemplateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new exam template",
)
async def create_template(
    body: TemplateCreate,
    teacher_id: TeacherId,
) -> TemplateResponse:
    sb = await get_supabase_client()

    row = {
        "teacher_id": teacher_id,
        "name": body.name,
        "subject": body.subject,
        "mode": body.mode,
        "max_score": body.max_score,
        "structure_json": {},
        "answer_key_json": {},
    }

    try:
        result = (
            await sb.table("exam_templates")
            .insert(row)
            .execute()
        )
    except Exception as exc:
        logger.error("Failed to create template: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create template",
        ) from exc

    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Insert returned no data",
        )

    return _row_to_response(result.data[0])


# ── POST /templates/{id}/upload ──────────────────────────────

_MODE_FILE_TYPES = {
    "integrated": {
        "auto": ("template_image_url", "integrated"),
        "integrated": ("template_image_url", "integrated"),
    },
    "separate_answer_sheet": {
        "auto": ("answer_sheet_template_url", "answer_sheet"),
        "answer_sheet": ("answer_sheet_template_url", "answer_sheet"),
        "question_book": ("question_book_url", "question_book"),
    },
}


@router.post(
    "/{template_id}/upload",
    response_model=TemplateUploadResponse,
    summary="Upload exam image / PDF for a template",
)
async def upload_template_image(
    template_id: str,
    file: UploadFile,
    teacher_id: TeacherId,
    file_type: str = Query(
        "auto",
        description="integrated | question_book | answer_sheet (auto = infer from mode)",
    ),
) -> TemplateUploadResponse:
    template = await _get_template_or_404(template_id, teacher_id)
    mode: str = template.get("mode", "integrated")

    # Resolve which DB column to update
    type_map = _MODE_FILE_TYPES.get(mode, _MODE_FILE_TYPES["integrated"])
    mapping = type_map.get(file_type) or type_map.get("auto")
    if mapping is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file_type '{file_type}' for mode '{mode}'",
        )
    db_field, resolved_type = mapping

    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No filename provided",
        )

    file_bytes = await file.read()

    storage = get_storage_service()
    try:
        image_url = await storage.upload_template_image(
            file_bytes=file_bytes,
            filename=file.filename,
            teacher_id=teacher_id,
            template_id=template_id,
            subfolder=resolved_type,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.error("Upload failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Image upload failed",
        ) from exc

    sb = await get_supabase_client()
    try:
        await (
            sb.table("exam_templates")
            .update({db_field: image_url})
            .eq("id", template_id)
            .execute()
        )
    except Exception as exc:
        logger.error("Failed to save image URL: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save image URL",
        ) from exc

    logger.info(
        "Template %s upload: field=%s url=%s", template_id, db_field, image_url
    )
    return TemplateUploadResponse(
        id=template_id,
        file_type=resolved_type,
        url_field=db_field,
        image_url=image_url,
        message=f"File uploaded successfully ({resolved_type})",
    )


# ── POST /templates/{id}/extract ─────────────────────────────

@router.post(
    "/{template_id}/extract",
    response_model=TemplateExtractResponse,
    summary="Extract exam structure from uploaded image(s) using AI Vision",
)
async def extract_template_structure(
    template_id: str,
    teacher_id: TeacherId,
) -> TemplateExtractResponse:
    template = await _get_template_or_404(template_id, teacher_id)
    mode: str = template.get("mode", "integrated")

    storage = get_storage_service()
    vision = get_vision_service()
    temp_paths: list[str] = []

    try:
        if mode == "integrated":
            image_url = template.get("template_image_url")
            if not image_url:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No image uploaded. Upload the exam image first.",
                )
            tmp = await storage.download_to_temp(image_url)
            temp_paths.append(tmp)
            structure = await vision.structure_exam_template(tmp)

        elif mode == "separate_answer_sheet":
            answer_sheet_raw = template.get("answer_sheet_template_url")
            if not answer_sheet_raw:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "No answer sheet uploaded. "
                        "Upload the answer sheet template first (required)."
                    ),
                )

            # Parse URL fields — may be a single URL or JSON array from PDF upload
            answer_sheet_urls = _parse_url_field(answer_sheet_raw)
            question_book_urls = _parse_url_field(template.get("question_book_url"))

            logger.info(
                "Template URLs: answer_sheet=%d, booklet=%d",
                len(answer_sheet_urls), len(question_book_urls),
            )

            # Download all answer sheet page images
            answer_sheet_paths: list[str] = []
            for url in answer_sheet_urls:
                tmp = await storage.download_to_temp(url)
                answer_sheet_paths.append(tmp)
                temp_paths.append(tmp)
            logger.info("Answer sheet: %d image(s) downloaded", len(answer_sheet_paths))

            # Download all question booklet page images
            booklet_paths: list[str] = []
            for url in question_book_urls:
                tmp = await storage.download_to_temp(url)
                booklet_paths.append(tmp)
                temp_paths.append(tmp)
            logger.info("Question booklet: %d image(s) downloaded", len(booklet_paths))

            total_images = len(answer_sheet_paths) + len(booklet_paths)
            logger.info(
                "Total images for Vision extraction: %d (answer_sheet=%d + booklet=%d)",
                total_images, len(answer_sheet_paths), len(booklet_paths),
            )

            structure = await vision.structure_exam_template_separate(
                answer_sheet_paths=answer_sheet_paths,
                booklet_paths=booklet_paths,
            )

        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown template mode: '{mode}'",
            )

    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Vision extraction failed: {exc}",
        ) from exc
    except Exception as exc:
        logger.exception("Extract failed for template %s", template_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="AI Vision processing failed",
        ) from exc
    finally:
        for path in temp_paths:
            if path and os.path.exists(path):
                os.unlink(path)

    # ── Normalize points_each to match declared total_points ──
    structure = _normalize_structure_points(structure)

    # ── Validate extraction completeness ────────────────────
    max_score = structure.get("max_score", 0)
    expected_score = float(template.get("max_score", 100))
    is_complete = max_score >= expected_score * 0.9  # 90% threshold
    extraction_status = "complete" if is_complete else "incomplete"
    missing_points = max(0, expected_score - max_score)

    logger.warning(
        "Extraction result for template %s: %s/%s pts - Status: %s",
        template_id, max_score, expected_score, extraction_status,
    )

    update_data: dict[str, Any] = {"structure_json": structure}
    if structure.get("name"):
        update_data["name"] = structure["name"]
    if structure.get("subject"):
        update_data["subject"] = structure["subject"]
    if structure.get("max_score"):
        update_data["max_score"] = structure["max_score"]

    sb = await get_supabase_client()
    try:
        await (
            sb.table("exam_templates")
            .update(update_data)
            .eq("id", template_id)
            .execute()
        )
    except Exception as exc:
        logger.error("Failed to save extracted structure: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save extracted structure",
        ) from exc

    return TemplateExtractResponse(
        id=template_id,
        structure=structure,
        message="Exam structure extracted successfully",
        extraction_status=extraction_status,
        missing_points=missing_points,
    )


# ── PUT /templates/{id}/structure ────────────────────────────

@router.put(
    "/{template_id}/structure",
    response_model=TemplateResponse,
    summary="Update the exam structure (manual correction after incomplete extraction)",
)
async def update_structure(
    template_id: str,
    body: StructureUpdate,
    teacher_id: TeacherId,
) -> TemplateResponse:
    await _get_template_or_404(template_id, teacher_id)

    update_data: dict[str, Any] = {
        "structure_json": body.structure,
        "max_score": body.structure.get("max_score", 0),
    }
    if body.structure.get("name"):
        update_data["name"] = body.structure["name"]
    if body.structure.get("subject"):
        update_data["subject"] = body.structure["subject"]

    sb = await get_supabase_client()
    try:
        result = (
            await sb.table("exam_templates")
            .update(update_data)
            .eq("id", template_id)
            .execute()
        )
    except Exception as exc:
        logger.error("Failed to update structure for template %s: %s", template_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update structure",
        ) from exc

    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Update returned no data",
        )

    logger.info("Structure updated manually for template %s", template_id)
    return _row_to_response(result.data[0])


# ── GET /templates ───────────────────────────────────────────

@router.get(
    "",
    response_model=TemplateListResponse,
    summary="List all templates for the current teacher",
)
async def list_templates(
    teacher_id: TeacherId,
) -> TemplateListResponse:
    sb = await get_supabase_client()

    try:
        result = (
            await sb.table("exam_templates")
            .select("*")
            .eq("teacher_id", teacher_id)
            .order("created_at", desc=True)
            .execute()
        )
    except Exception as exc:
        logger.error("Failed to list templates: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch templates",
        ) from exc

    rows = result.data or []
    return TemplateListResponse(
        templates=[_row_to_response(r) for r in rows],
        count=len(rows),
    )


# ── GET /templates/{id} ─────────────────────────────────────

@router.get(
    "/{template_id}",
    response_model=TemplateResponse,
    summary="Get template details",
)
async def get_template(
    template_id: str,
    teacher_id: TeacherId,
) -> TemplateResponse:
    row = await _get_template_or_404(template_id, teacher_id)
    return _row_to_response(row)


# ── PUT /templates/{id}/answer-key ───────────────────────────

def _validate_answer_key(
    answer_key: dict[str, Any],
    structure: dict[str, Any],
) -> list[str]:
    """Validate answer key entries against their expected question types.

    Returns a list of validation error strings (empty means valid).
    """
    if not answer_key:
        return ["Answer key cannot be empty — add at least 1 answer"]

    q_type_map: dict[str, str] = {}
    for section in structure.get("sections", []):
        for part in section.get("parts", []):
            q_type = part.get("type", "short_answer")
            for q_num in part.get("questions", []):
                q_type_map[str(q_num)] = q_type

    errors: list[str] = []
    valid_mc = {"A", "B", "C", "D"}
    valid_tf = {"True", "False", "true", "false", "TRUE", "FALSE"}

    for q_id, answer in answer_key.items():
        q_type = q_type_map.get(str(q_id))
        if q_type is None:
            continue  # Question not found in structure — skip type check

        if q_type == "multiple_choice":
            if not isinstance(answer, str) or answer.strip().upper() not in valid_mc:
                errors.append(
                    f"Q{q_id}: multiple_choice must be 'A', 'B', 'C', or 'D' (got '{answer}')"
                )
        elif q_type == "true_false":
            if not isinstance(answer, str) or answer.strip() not in valid_tf:
                errors.append(
                    f"Q{q_id}: true_false must be 'True' or 'False' (got '{answer}')"
                )
        elif q_type == "short_answer":
            if not isinstance(answer, str) or not answer.strip():
                errors.append(f"Q{q_id}: short_answer must be a non-empty string")
        elif q_type == "matching":
            if not isinstance(answer, dict):
                errors.append(
                    f"Q{q_id}: matching answer must be a dict like {{\"A\": \"1\", \"B\": \"2\"}}"
                )

    return errors


@router.put(
    "/{template_id}/answer-key",
    response_model=TemplateResponse,
    summary="Save or update the answer key for a template",
)
async def save_answer_key(
    template_id: str,
    body: AnswerKeyUpdate,
    teacher_id: TeacherId,
) -> TemplateResponse:
    template = await _get_template_or_404(template_id, teacher_id)

    # ── Validation ────────────────────────────────────────────
    answer_key = body.answer_key or {}
    if not answer_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Answer key cannot be empty — add at least 1 answer",
        )

    structure = template.get("structure_json") or {}
    validation_errors = _validate_answer_key(answer_key, structure)
    if validation_errors:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Answer key validation failed: {'; '.join(validation_errors)}",
        )

    sb = await get_supabase_client()
    try:
        result = (
            await sb.table("exam_templates")
            .update({
                "answer_key_json": answer_key,
                "answer_key_method": body.method,
            })
            .eq("id", template_id)
            .execute()
        )
    except Exception as exc:
        logger.error("Failed to save answer key for template %s: %s", template_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save answer key",
        ) from exc

    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Update returned no data",
        )

    logger.info(
        "Answer key saved: %d questions (template=%s, method=%s)",
        len(answer_key), template_id, body.method,
    )
    return _row_to_response(result.data[0])
