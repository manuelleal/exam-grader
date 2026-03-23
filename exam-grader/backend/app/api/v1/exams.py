import logging
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.database import get_supabase_client
from app.core.security import get_current_teacher_id
from app.schemas.exam import ExamBriefResponse, ExamListResponse, ExamReviewRequest, ExamResponse, ExamUpdateAnswersRequest
from app.schemas.result import ResultResponse
from app.services.grading_service import get_grading_service

logger = logging.getLogger(__name__)

router = APIRouter()

TeacherId = Annotated[str, Depends(get_current_teacher_id)]


# ── Helpers ──────────────────────────────────────────────────

async def _verify_exam_ownership(
    exam_id: str,
    teacher_id: str,
) -> dict[str, Any]:
    """Fetch an exam and verify teacher owns it via session → teacher_id."""
    sb = await get_supabase_client()

    # Fetch exam
    exam_result = (
        await sb.table("student_exams")
        .select("*")
        .eq("id", exam_id)
        .limit(1)
        .execute()
    )
    if not exam_result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Exam '{exam_id}' not found",
        )
    exam_row = exam_result.data[0]

    # Verify ownership via grading_sessions
    session_result = (
        await sb.table("grading_sessions")
        .select("teacher_id")
        .eq("id", exam_row["session_id"])
        .eq("teacher_id", teacher_id)
        .limit(1)
        .execute()
    )
    if not session_result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Exam '{exam_id}' not found",
        )

    return exam_row


async def _verify_session_ownership(
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


def _row_to_exam_response(row: dict[str, Any]) -> ExamResponse:
    """Convert a student_exams row to ExamResponse."""
    return ExamResponse(
        id=row["id"],
        session_id=row["session_id"],
        student_name=row.get("student_name"),
        student_id=row.get("student_id"),
        image_urls=row.get("image_urls") or [],
        page_count=row.get("page_count", 1),
        extracted_answers_json=row.get("extracted_answers_json"),
        status=row.get("status", "pending"),
        error_message=row.get("error_message"),
        needs_review_reason=row.get("needs_review_reason"),
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )


def _row_to_result_response(row: dict[str, Any]) -> ResultResponse:
    """Convert a grading_results row to ResultResponse."""
    return ResultResponse(
        id=row["id"],
        exam_id=row["exam_id"],
        total_score=float(row["total_score"]),
        max_score=float(row["max_score"]),
        percentage=float(row["percentage"]) if row.get("percentage") is not None else None,
        section_scores_json=row.get("section_scores_json"),
        feedback_json=row.get("feedback_json"),
        teacher_corrections_json=row.get("teacher_corrections_json"),
        final_score=float(row["final_score"]) if row.get("final_score") is not None else None,
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )


# ── GET /exams/{id} ──────────────────────────────────────────

@router.get(
    "/{exam_id}",
    response_model=ExamResponse,
    summary="Get a student exam with images and extracted answers",
)
async def get_exam(
    exam_id: str,
    teacher_id: TeacherId,
) -> ExamResponse:
    logger.info("Getting exam %s for teacher %s", exam_id, teacher_id)
    exam_row = await _verify_exam_ownership(exam_id, teacher_id)
    return _row_to_exam_response(exam_row)


# ── GET /exams/{id}/result ───────────────────────────────────

@router.get(
    "/{exam_id}/result",
    response_model=ResultResponse,
    summary="Get the grading result for a student exam",
)
async def get_exam_result(
    exam_id: str,
    teacher_id: TeacherId,
) -> ResultResponse:
    logger.info("Getting result for exam %s, teacher %s", exam_id, teacher_id)

    # Verify ownership
    await _verify_exam_ownership(exam_id, teacher_id)

    sb = await get_supabase_client()
    result = (
        await sb.table("grading_results")
        .select("*")
        .eq("exam_id", exam_id)
        .limit(1)
        .execute()
    )
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No grading result found for exam '{exam_id}'",
        )

    return _row_to_result_response(result.data[0])


# ── GET /sessions/{session_id}/exams ─────────────────────────
# NOTE: mounted under /exams but uses /sessions/{session_id}/exams path
# We register this in the sessions sub-path via a separate approach below.

@router.get(
    "/sessions/{session_id}",
    response_model=ExamListResponse,
    summary="List all exams in a session with score preview",
)
async def list_session_exams(
    session_id: str,
    teacher_id: TeacherId,
    exam_status: Optional[str] = Query(
        None,
        alias="status",
        description="Filter by status: pending, graded, review_needed, error",
    ),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> ExamListResponse:
    logger.info(
        "Listing exams for session %s, teacher %s (status=%s)",
        session_id, teacher_id, exam_status,
    )

    # Verify session ownership
    await _verify_session_ownership(session_id, teacher_id)

    sb = await get_supabase_client()

    # Query student exams
    query = (
        sb.table("student_exams")
        .select("*", count="exact")
        .eq("session_id", session_id)
        .order("created_at", desc=False)
        .range(offset, offset + limit - 1)
    )

    if exam_status:
        query = query.eq("status", exam_status)

    try:
        exams_result = await query.execute()
    except Exception as exc:
        logger.error("Failed to list exams for session %s: %s", session_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list exams",
        ) from exc

    exam_rows = exams_result.data or []
    total = exams_result.count if exams_result.count is not None else len(exam_rows)

    # Fetch score previews from grading_results for graded exams
    graded_exam_ids = [r["id"] for r in exam_rows if r.get("status") == "graded"]
    scores_map: dict[str, dict[str, float]] = {}

    if graded_exam_ids:
        try:
            scores_result = (
                await sb.table("grading_results")
                .select("exam_id, total_score, max_score, final_score")
                .in_("exam_id", graded_exam_ids)
                .execute()
            )
            for s in (scores_result.data or []):
                scores_map[s["exam_id"]] = {
                    "score": float(s["final_score"]) if s.get("final_score") is not None else float(s["total_score"]),
                    "max_score": float(s["max_score"]),
                }
        except Exception as exc:
            logger.warning("Failed to fetch score previews: %s", exc)

    # Build response
    exams: list[ExamBriefResponse] = []
    for row in exam_rows:
        score_info = scores_map.get(row["id"])
        exams.append(
            ExamBriefResponse(
                id=row["id"],
                session_id=row["session_id"],
                student_name=row.get("student_name"),
                status=row.get("status", "pending"),
                score_preview=score_info["score"] if score_info else None,
                max_score=score_info["max_score"] if score_info else None,
                needs_review_reason=row.get("needs_review_reason"),
                created_at=row.get("created_at"),
            )
        )

    return ExamListResponse(exams=exams, count=total)


# ── GET /exams/{id}/improvement-plan ─────────────────────────

@router.get(
    "/{exam_id}/improvement-plan",
    summary="Get AI-generated improvement plan for a student exam",
)
async def get_improvement_plan(
    exam_id: str,
    teacher_id: TeacherId,
) -> dict[str, Any]:
    logger.info("Getting improvement plan for exam %s, teacher %s", exam_id, teacher_id)

    # Verify ownership
    exam_row = await _verify_exam_ownership(exam_id, teacher_id)

    sb = await get_supabase_client()

    # Fetch grading result
    result_res = (
        await sb.table("grading_results")
        .select("*")
        .eq("exam_id", exam_id)
        .limit(1)
        .execute()
    )
    if not result_res.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No grading result found for exam '{exam_id}'",
        )
    result = result_res.data[0]

    # Fetch template structure
    session_res = (
        await sb.table("grading_sessions")
        .select("template_id")
        .eq("id", exam_row["session_id"])
        .limit(1)
        .execute()
    )
    template_id = session_res.data[0]["template_id"] if session_res.data else None

    structure: dict[str, Any] = {}
    if template_id:
        tmpl_res = (
            await sb.table("exam_templates")
            .select("structure_json")
            .eq("id", template_id)
            .limit(1)
            .execute()
        )
        if tmpl_res.data:
            structure = tmpl_res.data[0].get("structure_json", {})

    student_name = exam_row.get("student_name") or "Unknown Student"

    # Generate plan
    grading = get_grading_service()
    try:
        plan = await grading.generate_improvement_plan(
            student_results=result,
            template=structure,
            student_name=student_name,
        )
    except Exception as exc:
        logger.error("Failed to generate improvement plan for exam %s: %s", exam_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate improvement plan",
        ) from exc

    return {
        "exam_id": exam_id,
        "student_name": student_name,
        "plan": plan,
    }


# ── PATCH /exams/{id}/review-answers ─────────────────────────

def _extract_answer_value(answer: Any) -> Any:
    """Extract plain value from a confidence-annotated answer dict or plain string."""
    if isinstance(answer, dict):
        return answer.get("value")
    return answer


@router.patch(
    "/{exam_id}/review-answers",
    response_model=ExamResponse,
    summary="Submit teacher corrections for low-confidence answers and re-grade",
)
async def review_exam_answers(
    exam_id: str,
    body: ExamReviewRequest,
    teacher_id: TeacherId,
) -> ExamResponse:
    logger.info(
        "Teacher %s reviewing answers for exam %s (%d corrections)",
        teacher_id, exam_id, len(body.corrections),
    )

    exam_row = await _verify_exam_ownership(exam_id, teacher_id)

    if exam_row.get("status") != "review_needed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Exam is not in 'review_needed' status",
        )

    sb = await get_supabase_client()

    # Apply teacher corrections to extracted_answers_json
    answers: dict[str, Any] = dict(exam_row.get("extracted_answers_json") or {})
    for q_id, corrected_value in body.corrections.items():
        if q_id in answers and isinstance(answers[q_id], dict):
            answers[q_id] = {
                "value": corrected_value,
                "confidence": "high",
                "reviewed_by_teacher": True,
            }
        else:
            answers[q_id] = {"value": corrected_value, "confidence": "high", "reviewed_by_teacher": True}

    # Fetch template structure and answer key for re-grading
    session_res = (
        await sb.table("grading_sessions")
        .select("template_id")
        .eq("id", exam_row["session_id"])
        .limit(1)
        .execute()
    )
    template_id = session_res.data[0]["template_id"] if session_res.data else None

    structure: dict[str, Any] = {}
    answer_key: dict[str, Any] = {}
    max_score = 0.0
    if template_id:
        tmpl_res = (
            await sb.table("exam_templates")
            .select("*")
            .eq("id", template_id)
            .limit(1)
            .execute()
        )
        if tmpl_res.data:
            structure = tmpl_res.data[0].get("structure_json", {})
            answer_key = tmpl_res.data[0].get("answer_key_json", {}) or {}
            max_score = float(tmpl_res.data[0].get("max_score", 0))

    # Re-grade with corrected answers
    grading_svc = get_grading_service()
    total_score = 0.0
    section_scores: dict[str, Any] = {}
    question_feedback: dict[str, str] = {}

    for section in structure.get("sections", []):
        section_name = section.get("name", "Unknown")
        section_earned = 0.0
        section_max = 0.0

        for part in section.get("parts", []):
            q_type = part.get("type", "short_answer")
            points_each = float(part.get("points_each", 1))

            for q_num in part.get("questions", []):
                raw_ans = answers.get(str(q_num))
                student_ans = _extract_answer_value(raw_ans) or ""
                correct_ans = answer_key.get(str(q_num), "")
                section_max += points_each

                try:
                    grade_result = await grading_svc.grade_question(
                        question_type=q_type,
                        student_answer=student_ans,
                        correct_answer=correct_ans,
                        points=points_each,
                    )
                    earned = grade_result.get("points_earned", 0.0)
                    section_earned += earned
                    total_score += earned
                    feedback = grade_result.get("feedback", "")
                    if feedback:
                        question_feedback[str(q_num)] = feedback
                except Exception as exc:
                    logger.error("Error re-grading Q%s for exam %s: %s", q_num, exam_id, exc)

        section_scores[section_name] = {
            "earned": round(section_earned, 2),
            "max": round(section_max, 2),
        }

    # Upsert grading result
    grading_row = {
        "exam_id": exam_id,
        "total_score": round(total_score, 2),
        "max_score": max_score,
        "section_scores_json": section_scores,
        "feedback_json": {"question_feedback": question_feedback},
    }
    existing_result = (
        await sb.table("grading_results")
        .select("id")
        .eq("exam_id", exam_id)
        .limit(1)
        .execute()
    )
    try:
        if existing_result.data:
            await (
                sb.table("grading_results")
                .update(grading_row)
                .eq("exam_id", exam_id)
                .execute()
            )
        else:
            await sb.table("grading_results").insert(grading_row).execute()
    except Exception as exc:
        logger.error("Failed to save re-grading result for exam %s: %s", exam_id, exc)

    # Mark exam as graded and clear review flag
    try:
        await (
            sb.table("student_exams")
            .update({
                "status": "graded",
                "needs_review_reason": None,
                "extracted_answers_json": answers,
            })
            .eq("id", exam_id)
            .execute()
        )
    except Exception as exc:
        logger.error("Failed to mark exam %s as graded after review: %s", exam_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to finalize exam after review",
        ) from exc

    updated = (
        await sb.table("student_exams")
        .select("*")
        .eq("id", exam_id)
        .limit(1)
        .execute()
    )
    return _row_to_exam_response(updated.data[0])


# ── PATCH /exams/{id}/extracted-answers ───────────────────────

@router.patch(
    "/{exam_id}/extracted-answers",
    response_model=ExamResponse,
    summary="Update extracted answers (teacher correction)",
)
async def update_extracted_answers(
    exam_id: str,
    body: ExamUpdateAnswersRequest,
    teacher_id: TeacherId,
) -> ExamResponse:
    """Allows teacher to correct extracted answers before or after grading."""
    logger.info(
        "Teacher %s updating extracted answers for exam %s",
        teacher_id, exam_id,
    )

    await _verify_exam_ownership(exam_id, teacher_id)

    sb = await get_supabase_client()
    try:
        await (
            sb.table("student_exams")
            .update({"extracted_answers_json": body.answers})
            .eq("id", exam_id)
            .execute()
        )
    except Exception as exc:
        logger.error("Failed to update extracted answers for exam %s: %s", exam_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update answers",
        ) from exc

    updated = (
        await sb.table("student_exams")
        .select("*")
        .eq("id", exam_id)
        .limit(1)
        .execute()
    )
    return _row_to_exam_response(updated.data[0])


# ── POST /exams/{id}/regrade ──────────────────────────────────

@router.post(
    "/{exam_id}/regrade",
    summary="Re-grade an exam after manual answer corrections",
)
async def regrade_exam(
    exam_id: str,
    teacher_id: TeacherId,
) -> dict[str, Any]:
    """Re-grades an exam using the current extracted_answers_json."""
    logger.info(
        "Teacher %s requesting re-grade for exam %s",
        teacher_id, exam_id,
    )

    exam_row = await _verify_exam_ownership(exam_id, teacher_id)

    sb = await get_supabase_client()

    # Fetch template via session
    session_res = (
        await sb.table("grading_sessions")
        .select("template_id")
        .eq("id", exam_row["session_id"])
        .limit(1)
        .execute()
    )
    if not session_res.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )
    template_id = session_res.data[0]["template_id"]

    tmpl_res = (
        await sb.table("exam_templates")
        .select("*")
        .eq("id", template_id)
        .limit(1)
        .execute()
    )
    if not tmpl_res.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found",
        )
    template = tmpl_res.data[0]
    structure = template.get("structure_json", {})
    answer_key = template.get("answer_key_json", {}) or {}
    max_score = float(template.get("max_score", 0))

    answers = exam_row.get("extracted_answers_json") or {}

    # Re-grade
    grading_svc = get_grading_service()
    total_score = 0.0
    section_scores: dict[str, Any] = {}
    question_feedback: dict[str, str] = {}

    # Separate short_answer questions for batch AI call
    short_answer_items: list[tuple] = []
    section_data: list[dict[str, Any]] = []

    for section in structure.get("sections", []):
        section_name = section.get("name", "Unknown")
        section_earned = 0.0
        section_max = 0.0
        short_q_in_section: list[str] = []

        for part in section.get("parts", []):
            q_type = part.get("type", "short_answer")
            points_each = float(part.get("points_each", 1))

            for q_num in part.get("questions", []):
                raw_ans = answers.get(str(q_num))
                student_ans = _extract_answer_value(raw_ans) or ""
                correct_ans = answer_key.get(str(q_num), "")
                section_max += points_each

                if q_type == "short_answer":
                    short_answer_items.append(
                        (str(q_num), student_ans, correct_ans, points_each)
                    )
                    short_q_in_section.append(str(q_num))
                else:
                    try:
                        grade_result = await grading_svc.grade_question(
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
                            "Regrade failed for Q%s (exam %s): %s",
                            q_num, exam_id, exc,
                        )

        section_data.append({
            "name": section_name,
            "earned": section_earned,
            "max": section_max,
            "short_q": short_q_in_section,
        })

    # Batch grade short_answer questions
    batch_earned_map: dict[str, float] = {}
    if short_answer_items:
        logger.info(
            "Batch grading %d short-answer questions for regrade of exam %s",
            len(short_answer_items), exam_id,
        )
        batch_results = await grading_svc.grade_short_answers_batch(short_answer_items)
        for item, result in zip(short_answer_items, batch_results):
            q_num = item[0]
            earned = result.get("points_earned", 0.0)
            batch_earned_map[q_num] = earned
            total_score += earned
            fb = result.get("feedback", "")
            if fb:
                question_feedback[q_num] = fb

    # Build final section scores
    for sec in section_data:
        sec_earned = sec["earned"]
        for q_num in sec["short_q"]:
            sec_earned += batch_earned_map.get(q_num, 0.0)
        section_scores[sec["name"]] = {
            "earned": round(sec_earned, 2),
            "max": round(sec["max"], 2),
        }

    # Upsert grading result
    grading_row = {
        "exam_id": exam_id,
        "total_score": round(total_score, 2),
        "max_score": max_score,
        "section_scores_json": section_scores,
        "feedback_json": {"question_feedback": question_feedback},
    }
    existing_result = (
        await sb.table("grading_results")
        .select("id")
        .eq("exam_id", exam_id)
        .limit(1)
        .execute()
    )
    try:
        if existing_result.data:
            await (
                sb.table("grading_results")
                .update(grading_row)
                .eq("exam_id", exam_id)
                .execute()
            )
        else:
            await sb.table("grading_results").insert(grading_row).execute()
    except Exception as exc:
        logger.error("Failed to save re-grading result for exam %s: %s", exam_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save grading result",
        ) from exc

    # Update exam status
    try:
        await (
            sb.table("student_exams")
            .update({"status": "graded", "needs_review_reason": None})
            .eq("id", exam_id)
            .execute()
        )
    except Exception as exc:
        logger.error("Failed to update exam status after regrade %s: %s", exam_id, exc)

    logger.info(
        "Re-graded exam %s: %.2f/%.2f", exam_id, total_score, max_score
    )

    return {
        "message": "Re-graded successfully",
        "exam_id": exam_id,
        "total_score": round(total_score, 2),
        "max_score": max_score,
        "section_scores": section_scores,
    }
