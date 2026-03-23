import asyncio
import logging
import os
from typing import Annotated, Any, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, UploadFile, status
from fastapi.responses import Response

from app.core.database import get_supabase_client
from app.core.security import get_current_teacher_id
from app.schemas.session import (
    SessionCreate,
    SessionDetailResponse,
    SessionListResponse,
    SessionProcessResponse,
    SessionResponse,
    SessionStatusResponse,
    SessionUploadResponse,
    StudentExamBrief,
    TemplateInfo,
)
from app.services.export_service import get_export_service
from app.services.grading_service import get_grading_service
from app.services.grouping_service import (
    get_grouping_service,
    group_photos_by_student_sequential,
)
from app.services.ocr_service import get_ocr_service
from app.services.storage_service import get_storage_service
from app.services.vision_service import get_vision_service

logger = logging.getLogger(__name__)

router = APIRouter()

TeacherId = Annotated[str, Depends(get_current_teacher_id)]


# ── Helpers ──────────────────────────────────────────────────

def _row_to_response(row: dict[str, Any]) -> SessionResponse:
    """Convert a Supabase row dict to a SessionResponse."""
    return SessionResponse(
        id=row["id"],
        template_id=row["template_id"],
        teacher_id=row["teacher_id"],
        name=row["name"],
        total_students=row.get("total_students", 0),
        processed_students=row.get("processed_students", 0),
        status=row.get("status", "processing"),
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )


def _exam_row_to_brief(row: dict[str, Any]) -> StudentExamBrief:
    """Convert a student_exams row to StudentExamBrief."""
    return StudentExamBrief(
        id=row["id"],
        student_name=row.get("student_name"),
        status=row.get("status", "pending"),
        image_urls=row.get("image_urls") or [],
        error_message=row.get("error_message"),
        created_at=row.get("created_at"),
    )


async def _get_session_or_404(
    session_id: str,
    teacher_id: str,
) -> dict[str, Any]:
    """Fetch a session ensuring it belongs to the teacher."""
    sb = await get_supabase_client()
    result = (
        await sb.table("grading_sessions")
        .select("*")
        .eq("id", session_id)
        .eq("teacher_id", teacher_id)
        .limit(1)
        .execute()
    )
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found",
        )
    return result.data[0]


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


# ── POST /sessions ───────────────────────────────────────────

@router.post(
    "",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new grading session",
)
async def create_session(
    body: SessionCreate,
    teacher_id: TeacherId,
) -> SessionResponse:
    logger.info("Creating session '%s' for teacher %s", body.name, teacher_id)

    # Validate template exists and belongs to teacher
    await _get_template_or_404(body.template_id, teacher_id)

    sb = await get_supabase_client()
    row = {
        "template_id": body.template_id,
        "teacher_id": teacher_id,
        "name": body.name,
        "total_students": 0,
        "processed_students": 0,
        "status": "processing",
    }

    try:
        result = await sb.table("grading_sessions").insert(row).execute()
    except Exception as exc:
        logger.error("Failed to create session: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create grading session",
        ) from exc

    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Insert returned no data",
        )

    logger.info("Session created: %s", result.data[0]["id"])
    return _row_to_response(result.data[0])


# ── GET /sessions ────────────────────────────────────────────

@router.get(
    "",
    response_model=SessionListResponse,
    summary="List grading sessions for the current teacher",
)
async def list_sessions(
    teacher_id: TeacherId,
    template_id: Optional[str] = Query(None, description="Filter by template"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> SessionListResponse:
    logger.info("Listing sessions for teacher %s (template=%s)", teacher_id, template_id)

    sb = await get_supabase_client()

    query = (
        sb.table("grading_sessions")
        .select("*", count="exact")
        .eq("teacher_id", teacher_id)
        .order("created_at", desc=True)
        .range(offset, offset + limit - 1)
    )

    if template_id:
        query = query.eq("template_id", template_id)

    try:
        result = await query.execute()
    except Exception as exc:
        logger.error("Failed to list sessions: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list sessions",
        ) from exc

    sessions = [_row_to_response(r) for r in (result.data or [])]
    total = result.count if result.count is not None else len(sessions)

    return SessionListResponse(sessions=sessions, count=total)


# ── GET /sessions/{id} ───────────────────────────────────────

@router.get(
    "/{session_id}",
    response_model=SessionDetailResponse,
    summary="Get session details with template info and student exams",
)
async def get_session(
    session_id: str,
    teacher_id: TeacherId,
) -> SessionDetailResponse:
    logger.info("Getting session %s for teacher %s", session_id, teacher_id)

    session_row = await _get_session_or_404(session_id, teacher_id)
    sb = await get_supabase_client()

    # Fetch template info
    template_info: Optional[TemplateInfo] = None
    try:
        tmpl_result = (
            await sb.table("exam_templates")
            .select("id, name, subject, mode, max_score")
            .eq("id", session_row["template_id"])
            .limit(1)
            .execute()
        )
        if tmpl_result.data:
            t = tmpl_result.data[0]
            template_info = TemplateInfo(
                id=t["id"],
                name=t["name"],
                subject=t["subject"],
                mode=t["mode"],
                max_score=float(t["max_score"]),
            )
    except Exception as exc:
        logger.warning("Failed to fetch template info: %s", exc)

    # Fetch student exams
    student_exams: list[StudentExamBrief] = []
    try:
        exams_result = (
            await sb.table("student_exams")
            .select("*")
            .eq("session_id", session_id)
            .order("created_at", desc=False)
            .execute()
        )
        student_exams = [_exam_row_to_brief(r) for r in (exams_result.data or [])]
    except Exception as exc:
        logger.warning("Failed to fetch student exams: %s", exc)

    return SessionDetailResponse(
        id=session_row["id"],
        template_id=session_row["template_id"],
        teacher_id=session_row["teacher_id"],
        name=session_row["name"],
        total_students=session_row.get("total_students", 0),
        processed_students=session_row.get("processed_students", 0),
        status=session_row.get("status", "processing"),
        created_at=session_row.get("created_at"),
        updated_at=session_row.get("updated_at"),
        template=template_info,
        student_exams=student_exams,
    )


# ── POST /sessions/{id}/upload ───────────────────────────────

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif", "application/pdf"}
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB (PDFs can be larger)


@router.post(
    "/{session_id}/upload",
    response_model=SessionUploadResponse,
    summary="Upload a batch of student exam photos",
)
async def upload_student_photos(
    session_id: str,
    teacher_id: TeacherId,
    files: list[UploadFile],
) -> SessionUploadResponse:
    """Upload student exam photos OR PDFs.

    Accepts:
    - Multiple JPG/PNG/WEBP images
    - 1 or more multi-page PDFs (converted to images)
    - Mix of both
    """
    logger.info(
        "Uploading %d files to session %s for teacher %s",
        len(files), session_id, teacher_id,
    )

    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No files provided",
        )

    session_row = await _get_session_or_404(session_id, teacher_id)
    sb = await get_supabase_client()
    storage = get_storage_service()

    created_exams: list[StudentExamBrief] = []

    for idx, file in enumerate(files, 1):
        logger.info("╔═══ FILE %d/%d ═══╗", idx, len(files))
        logger.info("║ Filename: %s", file.filename)
        logger.info("║ Content-Type: %s", file.content_type)

        # Validate content type
        if file.content_type not in ALLOWED_CONTENT_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported file type '{file.content_type}' for '{file.filename}'. "
                       f"Allowed: {', '.join(sorted(ALLOWED_CONTENT_TYPES))}",
            )

        # Read and validate size
        file_bytes = await file.read()
        if len(file_bytes) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File '{file.filename}' is empty",
            )
        if len(file_bytes) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File '{file.filename}' exceeds {MAX_FILE_SIZE // (1024 * 1024)} MB limit",
            )

        logger.info("║ Size: %d bytes (%.1f KB)", len(file_bytes), len(file_bytes) / 1024)

        if file.content_type == "application/pdf":
            # PDF -> convert to images, then upload each
            logger.info("║ → PDF detected — converting to images...")
            import tempfile as _tempfile

            from app.services.pdf_service import get_pdf_service

            pdf_service = get_pdf_service()

            # Save PDF to temp file
            pdf_tmp = _tempfile.NamedTemporaryFile(
                delete=False, suffix=".pdf", prefix="upload_"
            )
            pdf_tmp.write(file_bytes)
            pdf_tmp.close()

            try:
                image_paths = await pdf_service.convert_pdf_to_images(pdf_tmp.name)
                logger.info(
                    "PDF '%s' converted to %d images", file.filename, len(image_paths)
                )

                for img_path in image_paths:
                    try:
                        with open(img_path, "rb") as f:
                            img_bytes = f.read()
                        img_filename = os.path.basename(img_path)
                        image_url = await storage.upload_student_exam_image(
                            file_bytes=img_bytes,
                            filename=img_filename,
                            teacher_id=teacher_id,
                            session_id=session_id,
                        )

                        exam_row = {
                            "session_id": session_id,
                            "image_urls": [image_url],
                            "page_count": 1,
                            "status": "pending",
                        }
                        exam_result = await sb.table("student_exams").insert(exam_row).execute()
                        if exam_result.data:
                            created_exams.append(_exam_row_to_brief(exam_result.data[0]))
                    except Exception as exc:
                        logger.error("Failed to upload PDF page %s: %s", img_path, exc)
                    finally:
                        try:
                            os.unlink(img_path)
                        except OSError:
                            pass

            except Exception as exc:
                logger.error("Failed to convert PDF '%s': %s", file.filename, exc)
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to convert PDF '{file.filename}': {exc}",
                ) from exc
            finally:
                try:
                    os.unlink(pdf_tmp.name)
                except OSError:
                    pass

        else:
            # Regular image -> upload directly
            try:
                image_url = await storage.upload_student_exam_image(
                    file_bytes=file_bytes,
                    filename=file.filename or "exam.jpg",
                    teacher_id=teacher_id,
                    session_id=session_id,
                )
            except Exception as exc:
                logger.error("Failed to upload '%s': %s", file.filename, exc)
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to upload '{file.filename}': {exc}",
                ) from exc

            # Create student_exam record with status "pending"
            exam_row = {
                "session_id": session_id,
                "image_urls": [image_url],
                "page_count": 1,
                "status": "pending",
            }

            try:
                exam_result = await sb.table("student_exams").insert(exam_row).execute()
            except Exception as exc:
                logger.error("Failed to insert student_exam: %s", exc)
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to save student exam record",
                ) from exc

            if exam_result.data:
                created_exams.append(_exam_row_to_brief(exam_result.data[0]))

    # Update total_students on session
    new_total = session_row.get("total_students", 0) + len(created_exams)
    try:
        await (
            sb.table("grading_sessions")
            .update({"total_students": new_total})
            .eq("id", session_id)
            .execute()
        )
    except Exception as exc:
        logger.warning("Failed to update total_students: %s", exc)

    logger.info(
        "Uploaded %d file(s) to session %s, total_students=%d",
        len(created_exams), session_id, new_total,
    )

    return SessionUploadResponse(
        session_id=session_id,
        uploaded=len(created_exams),
        student_exams=created_exams,
        message=f"{len(created_exams)} exam(s) uploaded successfully",
    )


# ── POST /sessions/{id}/process ──────────────────────────────

MAX_CONCURRENT_STUDENTS = 5  # Max students graded in parallel


def _get_answer_value(answer: Any) -> Any:
    """Extract plain answer value from either a string or a confidence-annotated dict."""
    if isinstance(answer, dict):
        return answer.get("value")
    return answer


def _get_low_confidence_questions(answers: dict[str, Any]) -> list[str]:
    """Return question IDs where confidence is 'low'."""
    return [
        q_id for q_id, ans in answers.items()
        if isinstance(ans, dict) and ans.get("confidence") == "low"
    ]


async def _grade_one_student(
    sb: Any,
    grading: Any,
    student_name: str,
    answers: dict[str, Any],
    exam_row: dict[str, Any],
    structure: dict[str, Any],
    answer_key: dict[str, Any],
    max_score: float,
    session_id: str,
    semaphore: asyncio.Semaphore,
) -> dict[str, Any]:
    """Grade one student's exam, save result, and update DB status."""
    exam_id = exam_row["id"]

    async with semaphore:
        logger.info(
            "Processing student '%s' (exam %s) in session %s",
            student_name, exam_id, session_id,
        )

        low_confidence_qs = _get_low_confidence_questions(answers)
        has_review = bool(low_confidence_qs)

        try:
            await (
                sb.table("student_exams")
                .update({
                    "student_name": student_name,
                    "extracted_answers_json": answers,
                    "status": "processing",
                })
                .eq("id", exam_id)
                .execute()
            )
        except Exception as exc:
            logger.error("Failed to mark exam %s as processing: %s", exam_id, exc)

        try:
            total_score = 0.0
            section_scores: dict[str, Any] = {}
            question_feedback: dict[str, str] = {}

            # Separate short_answer questions for batch AI call
            short_answer_items: list[tuple] = []  # (q_num, student_ans, correct_ans, points)
            # Per-section data for score assembly after batch
            section_data: list[dict[str, Any]] = []

            for section in structure.get("sections", []):
                section_name = section.get("name", "Unknown")
                section_earned = 0.0
                section_max = 0.0
                short_q_in_section: list[str] = []  # q_nums that are short_answer

                for part in section.get("parts", []):
                    q_type = part.get("type", "short_answer")
                    points_each = float(part.get("points_each", 1))

                    for q_num in part.get("questions", []):
                        raw_ans = answers.get(str(q_num))
                        student_ans = _get_answer_value(raw_ans) or ""
                        correct_ans = answer_key.get(str(q_num), "")
                        section_max += points_each

                        if q_type == "short_answer":
                            short_answer_items.append(
                                (str(q_num), student_ans, correct_ans, points_each)
                            )
                            short_q_in_section.append(str(q_num))
                        else:
                            try:
                                grade_result = await grading.grade_question(
                                    question_type=q_type,
                                    student_answer=student_ans,
                                    correct_answer=correct_ans,
                                    points=points_each,
                                )
                                earned = grade_result.get("points_earned", 0.0)
                                section_earned += earned
                                total_score += earned
                                fb = grade_result.get("feedback", "")
                                if fb:
                                    question_feedback[str(q_num)] = fb
                            except Exception as exc:
                                logger.error(
                                    "Grading failed for Q%s (student '%s'): %s",
                                    q_num, student_name, exc,
                                )

                section_data.append({
                    "name": section_name,
                    "earned": section_earned,
                    "max": section_max,
                    "short_q": short_q_in_section,
                })

            # Batch grade all short_answer questions in one AI call
            batch_earned_map: dict[str, float] = {}
            if short_answer_items:
                logger.info(
                    "Batch grading %d short-answer questions for '%s'",
                    len(short_answer_items), student_name,
                )
                batch_results = await grading.grade_short_answers_batch(short_answer_items)
                for item, result in zip(short_answer_items, batch_results):
                    q_num = item[0]
                    earned = result.get("points_earned", 0.0)
                    batch_earned_map[q_num] = earned
                    total_score += earned
                    fb = result.get("feedback", "")
                    if fb:
                        question_feedback[q_num] = fb

            # Build final section scores (add batch short_answer results)
            for sec in section_data:
                sec_earned = sec["earned"]
                for q_num in sec["short_q"]:
                    sec_earned += batch_earned_map.get(q_num, 0.0)
                section_scores[sec["name"]] = {
                    "earned": round(sec_earned, 2),
                    "max": round(sec["max"], 2),
                }

            # Save grading result
            grading_row = {
                "exam_id": exam_id,
                "total_score": round(total_score, 2),
                "max_score": max_score,
                "section_scores_json": section_scores,
                "feedback_json": {"question_feedback": question_feedback},
            }
            try:
                await sb.table("grading_results").insert(grading_row).execute()
            except Exception as exc:
                logger.error(
                    "Failed to insert grading result for exam %s: %s", exam_id, exc
                )

            # Mark exam as graded / review_needed
            final_status = "review_needed" if has_review else "graded"
            review_reason = (
                f"Questions need review: {', '.join(low_confidence_qs)}"
                if has_review else None
            )
            try:
                await (
                    sb.table("student_exams")
                    .update({
                        "status": final_status,
                        "needs_review_reason": review_reason,
                        "error_message": None,
                    })
                    .eq("id", exam_id)
                    .execute()
                )
            except Exception as exc:
                logger.error(
                    "Failed to update exam status for %s: %s", exam_id, exc
                )

            logger.info(
                "Student '%s' graded: %.2f/%.2f (status=%s)",
                student_name, total_score, max_score, final_status,
            )
            return {"exam_id": exam_id, "student_name": student_name, "status": final_status}

        except Exception as exc:
            error_msg = str(exc)
            logger.exception(
                "Grading failed for student '%s' (exam %s): %s", student_name, exam_id, exc
            )
            try:
                await (
                    sb.table("student_exams")
                    .update({
                        "status": "error",
                        "error_message": f"Grading failed: {error_msg}",
                    })
                    .eq("id", exam_id)
                    .execute()
                )
            except Exception as db_exc:
                logger.error(
                    "Failed to save error status for exam %s: %s", exam_id, db_exc
                )
            return {
                "exam_id": exam_id,
                "student_name": student_name,
                "status": "error",
                "error": error_msg,
            }


async def _process_session_background(session_id: str, teacher_id: str) -> None:
    """Background task: group → extract → grade (parallel) → save results.

    FLOW (v2 — sequential grouping by URL):
    1. Fetch all pending student_exam rows
    2. Collect ALL image URLs in upload order
    3. Run sequential grouping on URLs (name → new student, no name → continues)
    4. Consolidate: keep 1 exam_row per student, merge URLs, delete orphans
    5. Extract answers (vision) for each student
    6. Grade each student in parallel
    """
    logger.info("╔═══ PROCESS SESSION START: %s ═══╗", session_id)

    sb = await get_supabase_client()
    storage = get_storage_service()
    ocr_svc = get_ocr_service()
    vision_svc = get_vision_service()
    grouping = get_grouping_service()
    grading = get_grading_service()
    temp_paths: list[str] = []  # defined outside try so finally can clean up

    try:
        # ── 1. Fetch session and template ────────────────────────
        session_result = (
            await sb.table("grading_sessions")
            .select("*")
            .eq("id", session_id)
            .limit(1)
            .execute()
        )
        if not session_result.data:
            logger.error("Session %s not found during processing", session_id)
            return
        session_row = session_result.data[0]

        tmpl_result = (
            await sb.table("exam_templates")
            .select("*")
            .eq("id", session_row["template_id"])
            .limit(1)
            .execute()
        )
        if not tmpl_result.data:
            logger.error("Template not found for session %s", session_id)
            await _mark_session_failed(sb, session_id, "Template not found")
            return
        template = tmpl_result.data[0]
        structure = template.get("structure_json", {})
        answer_key = template.get("answer_key_json", {})

        # Normalize points_each so calculated totals match declared total_points
        from app.api.v1.templates import _normalize_structure_points
        structure = _normalize_structure_points(structure)
        max_score = float(structure.get("max_score", 0)) or float(template.get("max_score", 0))

        logger.info("║ Template: %s | max_score: %s", template.get("name"), max_score)
        logger.info("║ Structure sections: %d", len(structure.get("sections", [])))
        logger.info("║ Answer key questions: %d", len(answer_key))

        # ── 2. Fetch ALL pending student exams ───────────────────
        exams_result = (
            await sb.table("student_exams")
            .select("*")
            .eq("session_id", session_id)
            .eq("status", "pending")
            .order("created_at")
            .execute()
        )
        pending_exams = exams_result.data or []
        if not pending_exams:
            logger.info("║ No pending exams in session %s", session_id)
            await (
                sb.table("grading_sessions")
                .update({"status": "completed"})
                .eq("id", session_id)
                .execute()
            )
            return

        # ── 3. Collect ALL image URLs in upload order ────────────
        all_urls: list[str] = []
        url_to_exam_id: dict[str, str] = {}  # URL -> exam_row ID
        all_exam_ids: list[str] = []

        for exam in pending_exams:
            exam_id = exam["id"]
            all_exam_ids.append(exam_id)
            urls = exam.get("image_urls") or []
            for url in urls:
                all_urls.append(url)
                url_to_exam_id[url] = exam_id

        logger.info("║ Pending exams: %d | Total URLs: %d", len(pending_exams), len(all_urls))
        for i, url in enumerate(all_urls, 1):
            logger.info("║   URL %d: %s (exam_row=%s)", i, url[:80], url_to_exam_id[url][:8])

        if not all_urls:
            logger.error("║ No image URLs found for session %s", session_id)
            await _mark_session_failed(sb, session_id, "No images found")
            return

        # ── 4. SEQUENTIAL GROUPING by URL ────────────────────────
        logger.info("║ ▶ Starting SEQUENTIAL GROUPING on %d URLs...", len(all_urls))
        student_groups = await group_photos_by_student_sequential(
            photo_urls=all_urls,
            ocr_service=ocr_svc,
            storage_service=storage,
            vision_service=vision_svc,
        )

        logger.info("║ ◀ Grouping result: %d student(s)", len(student_groups))
        for g in student_groups:
            logger.info(
                "║   → %s: %d page(s) %s",
                g["student_name"], g["page_count"],
                [u[:50] for u in g["photo_urls"]],
            )

        # ── 5. Consolidate exam_rows ─────────────────────────────
        # For each student group: keep FIRST exam_row, merge all URLs into it,
        # delete the rest as orphans.
        student_exam_map: dict[str, dict[str, Any]] = {}  # student_name -> exam_row
        orphan_exam_ids: set[str] = set(all_exam_ids)

        for group in student_groups:
            student_name = group["student_name"]
            photo_urls = group["photo_urls"]
            page_count = group["page_count"]

            # Pick the first exam_row associated with this group's first URL
            first_url = photo_urls[0]
            primary_exam_id = url_to_exam_id.get(first_url)
            if not primary_exam_id:
                logger.warning("║ No exam_row for URL %s — skipping student %s", first_url, student_name)
                continue

            # Remove ONLY the primary from orphan list; other exam_ids that
            # contributed URLs to this group stay as orphans to be deleted.
            orphan_exam_ids.discard(primary_exam_id)

            # Update primary exam_row with all URLs and student name
            try:
                await (
                    sb.table("student_exams")
                    .update({
                        "student_name": student_name,
                        "image_urls": photo_urls,
                        "page_count": page_count,
                        "status": "processing",
                    })
                    .eq("id", primary_exam_id)
                    .execute()
                )
                logger.info(
                    "║ ✓ Consolidated '%s' → exam %s (%d pages)",
                    student_name, primary_exam_id[:8], page_count,
                )
            except Exception as exc:
                logger.error("║ ✗ Failed to update exam %s: %s", primary_exam_id, exc)
                continue

            # Find the full exam row for grading
            primary_row = next(
                (e for e in pending_exams if e["id"] == primary_exam_id), None
            )
            if primary_row:
                primary_row["image_urls"] = photo_urls
                primary_row["page_count"] = page_count
                student_exam_map[student_name] = primary_row

        # Delete orphan exam_rows (photos that got merged into another student's record)
        for orphan_id in orphan_exam_ids:
            try:
                await sb.table("student_exams").delete().eq("id", orphan_id).execute()
                logger.info("║ 🗑 Deleted orphan exam_row %s", orphan_id[:8])
            except Exception as exc:
                logger.warning("║ Could not delete orphan %s: %s", orphan_id, exc)

        logger.info(
            "║ Consolidation: %d student(s) kept, %d orphan(s) removed",
            len(student_exam_map), len(orphan_exam_ids),
        )

        if not student_exam_map:
            logger.error("║ No students after consolidation — aborting")
            await _mark_session_failed(sb, session_id, "No students found after grouping")
            return

        # ── 6. Extract answers per student (merge pages) ─────────
        logger.info("║ ▶ Extracting answers for %d student(s)...", len(student_exam_map))
        # Build grouped dict in old format for merge_student_pages
        grouped_for_merge: dict[str, list[str]] = {}

        for student_name, exam_row in student_exam_map.items():
            urls = exam_row.get("image_urls") or []
            local_paths: list[str] = []
            for url in urls:
                try:
                    temp_path = await storage.download_to_temp(url)
                    temp_paths.append(temp_path)
                    local_paths.append(temp_path)
                except Exception as exc:
                    logger.error("║ Failed to download %s: %s", url, exc)
            grouped_for_merge[student_name] = local_paths
            logger.info(
                "║   %s: %d local file(s) downloaded for answer extraction",
                student_name, len(local_paths),
            )

        student_answers = await grouping.merge_student_pages(grouped_for_merge, structure)

        for name, answers in student_answers.items():
            logger.info(
                "║   %s: %d answer(s) extracted → %s",
                name, len(answers), dict(list(answers.items())[:5]),
            )

        # ── 7. Grade all students in parallel ────────────────────
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_STUDENTS)
        tasks = []
        for student_name, answers in student_answers.items():
            exam_row = student_exam_map.get(student_name)
            if not exam_row:
                logger.warning("║ No exam_row for student '%s' — skipping", student_name)
                continue

            logger.info(
                "║ ▶ Queueing grading for '%s' (exam %s): %d answers",
                student_name, exam_row["id"][:8], len(answers),
            )
            tasks.append(
                _grade_one_student(
                    sb, grading, student_name, answers, exam_row,
                    structure, answer_key, max_score, session_id, semaphore,
                )
            )

        logger.info(
            "║ Grading %d student(s) in parallel (max_concurrent=%d)",
            len(tasks), MAX_CONCURRENT_STUDENTS,
        )
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # ── 8. Tally results and mark session completed ──────────
        processed_count = sum(
            1 for r in results
            if isinstance(r, dict) and r.get("status") in ("graded", "review_needed")
        )
        error_count = sum(
            1 for r in results
            if isinstance(r, Exception)
            or (isinstance(r, dict) and r.get("status") == "error")
        )

        await (
            sb.table("grading_sessions")
            .update({
                "status": "completed",
                "processed_students": processed_count,
                "total_students": len(student_answers),
            })
            .eq("id", session_id)
            .execute()
        )

        logger.info("╠═══ SESSION %s COMPLETE ═══╣", session_id)
        logger.info("║ Students graded: %d | Errors: %d", processed_count, error_count)
        for r in results:
            if isinstance(r, dict):
                logger.info(
                    "║   %s → %s",
                    r.get("student_name", "?"), r.get("status", "?"),
                )
            elif isinstance(r, Exception):
                logger.error("║   Exception: %s", r)
        logger.info("╚" + "═" * 51 + "╝")

    except Exception as exc:
        logger.exception("Session %s processing failed: %s", session_id, exc)
        try:
            await _mark_session_failed(sb, session_id, str(exc))
        except Exception:
            logger.exception("Failed to mark session %s as failed", session_id)

    finally:
        # Clean up temp files
        for path in temp_paths:
            try:
                os.unlink(path)
            except OSError:
                pass


async def _mark_session_failed(sb: Any, session_id: str, reason: str) -> None:
    """Mark a session as failed."""
    logger.error("Marking session %s as failed: %s", session_id, reason)
    await (
        sb.table("grading_sessions")
        .update({"status": "failed"})
        .eq("id", session_id)
        .execute()
    )


@router.post(
    "/{session_id}/process",
    response_model=SessionProcessResponse,
    summary="Process entire session (background job)",
)
async def process_session(
    session_id: str,
    teacher_id: TeacherId,
    background_tasks: BackgroundTasks,
) -> SessionProcessResponse:
    logger.info("Starting processing for session %s", session_id)

    session_row = await _get_session_or_404(session_id, teacher_id)

    sb = await get_supabase_client()

    # Allow reprocessing: if session was completed or failed, reset exams to pending
    current_status = session_row.get("status", "")
    if current_status in ("completed", "failed"):
        logger.info("Reprocessing session %s (was '%s') — resetting exams to pending", session_id, current_status)
        try:
            await (
                sb.table("student_exams")
                .update({"status": "pending", "error_message": None, "extracted_answers_json": None})
                .eq("session_id", session_id)
                .execute()
            )
            # Delete old grading results
            old_exams = await sb.table("student_exams").select("id").eq("session_id", session_id).execute()
            for ex in (old_exams.data or []):
                await sb.table("grading_results").delete().eq("exam_id", ex["id"]).execute()
        except Exception as exc:
            logger.error("Failed to reset exams for reprocessing: %s", exc)

    # ── Validate template has answer key ─────────────────────
    tmpl_result = (
        await sb.table("exam_templates")
        .select("answer_key_json")
        .eq("id", session_row["template_id"])
        .limit(1)
        .execute()
    )
    if tmpl_result.data:
        answer_key = tmpl_result.data[0].get("answer_key_json") or {}
        if not answer_key:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot process: template has no answer key. Set the answer key first.",
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot process: template not found.",
        )

    # ── Validate there are exams to process ──────────────────
    exams_check = (
        await sb.table("student_exams")
        .select("id")
        .eq("session_id", session_id)
        .eq("status", "pending")
        .limit(1)
        .execute()
    )
    if not exams_check.data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot process: no pending exams. Upload photos first or check if session needs reset.",
        )

    # Update status to processing
    try:
        await (
            sb.table("grading_sessions")
            .update({"status": "processing"})
            .eq("id", session_id)
            .execute()
        )
    except Exception as exc:
        logger.error("Failed to update session status: %s", exc)

    background_tasks.add_task(_process_session_background, session_id, teacher_id)
    logger.info("Session %s queued for background processing", session_id)

    return SessionProcessResponse(
        session_id=session_id,
        processing_status="processing",
        message="Session processing started in background",
    )


# ── GET /sessions/{id}/status ────────────────────────────────

@router.get(
    "/{session_id}/status",
    response_model=SessionStatusResponse,
    summary="Get session processing status",
)
async def get_session_status(
    session_id: str,
    teacher_id: TeacherId,
) -> SessionStatusResponse:
    session_row = await _get_session_or_404(session_id, teacher_id)
    sb = await get_supabase_client()

    total = 0
    processed = 0
    pending = 0
    failed = 0
    current_processing: Optional[str] = None
    errors: list[dict] = []

    try:
        exams_result = (
            await sb.table("student_exams")
            .select("id, status, student_name, error_message")
            .eq("session_id", session_id)
            .execute()
        )
        for exam in (exams_result.data or []):
            total += 1
            exam_status = exam.get("status", "pending")
            if exam_status in ("graded", "review_needed"):
                processed += 1
            elif exam_status == "processing":
                pending += 1
                if current_processing is None:
                    current_processing = (
                        exam.get("student_name") or exam.get("id")
                    )
            elif exam_status == "pending":
                pending += 1
            elif exam_status == "error":
                failed += 1
                errors.append({
                    "exam_id": exam["id"],
                    "student_name": exam.get("student_name"),
                    "error": exam.get("error_message") or "Unknown error",
                })
    except Exception as exc:
        logger.error("Failed to fetch exam statuses: %s", exc)

    session_status = session_row.get("status", "processing")
    progress_percentage = 0
    if total > 0:
        progress_percentage = round((processed / total) * 100)
    if session_status == "completed":
        progress_percentage = 100

    # Rough ETA: assume ~15 seconds per remaining exam
    estimated_time_remaining: Optional[int] = None
    if pending > 0 and session_status == "processing":
        estimated_time_remaining = max(1, (pending * 15) // MAX_CONCURRENT_STUDENTS)

    return SessionStatusResponse(
        session_id=session_id,
        status=session_status,
        total=total,
        processed=processed,
        pending=pending,
        failed=failed,
        current_processing=current_processing,
        progress_percentage=progress_percentage,
        estimated_time_remaining=estimated_time_remaining,
        errors=errors,
    )


# ── GET /sessions/{id}/export ────────────────────────────────

@router.get(
    "/{session_id}/export",
    summary="Export session data (Excel, CSV, or PDF ZIP)",
)
async def export_session(
    session_id: str,
    teacher_id: TeacherId,
    format: str = Query("excel", description="Export format: excel, csv, pdf_individual"),
) -> Response:
    logger.info("Exporting session %s as %s for teacher %s", session_id, format, teacher_id)

    # Validate session ownership
    await _get_session_or_404(session_id, teacher_id)

    export_svc = get_export_service()

    try:
        if format == "excel":
            data = await export_svc.export_session_to_excel(session_id, teacher_id)
            return Response(
                content=data,
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers={"Content-Disposition": f'attachment; filename="session_{session_id}.xlsx"'},
            )

        elif format == "csv":
            csv_str = await export_svc.export_session_to_csv(session_id, teacher_id)
            return Response(
                content=csv_str.encode("utf-8"),
                media_type="text/csv; charset=utf-8",
                headers={"Content-Disposition": f'attachment; filename="session_{session_id}.csv"'},
            )

        elif format == "pdf_individual":
            zip_data = await export_svc.export_session_pdfs_zip(session_id, teacher_id)
            return Response(
                content=zip_data,
                media_type="application/zip",
                headers={"Content-Disposition": f'attachment; filename="session_{session_id}_plans.zip"'},
            )

        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported format '{format}'. Use: excel, csv, pdf_individual",
            )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Export failed for session %s: %s", session_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Export failed: {exc}",
        ) from exc
