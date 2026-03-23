import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.database import get_supabase_client
from app.core.security import get_current_teacher_id
from app.schemas.result import ResultCorrectionRequest, ResultCorrectionResponse

logger = logging.getLogger(__name__)

router = APIRouter()

TeacherId = Annotated[str, Depends(get_current_teacher_id)]


# ── Helpers ──────────────────────────────────────────────────

async def _get_result_with_ownership(
    result_id: str,
    teacher_id: str,
) -> dict[str, Any]:
    """Fetch a grading result and verify teacher ownership via exam → session."""
    sb = await get_supabase_client()

    # Fetch result
    result_resp = (
        await sb.table("grading_results")
        .select("*")
        .eq("id", result_id)
        .limit(1)
        .execute()
    )
    if not result_resp.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Result '{result_id}' not found",
        )
    result_row = result_resp.data[0]

    # Fetch exam to get session_id
    exam_resp = (
        await sb.table("student_exams")
        .select("session_id")
        .eq("id", result_row["exam_id"])
        .limit(1)
        .execute()
    )
    if not exam_resp.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Result '{result_id}' not found",
        )

    # Verify teacher owns the session
    session_resp = (
        await sb.table("grading_sessions")
        .select("teacher_id")
        .eq("id", exam_resp.data[0]["session_id"])
        .eq("teacher_id", teacher_id)
        .limit(1)
        .execute()
    )
    if not session_resp.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Result '{result_id}' not found",
        )

    return result_row


# ── PUT /results/{id}/correct ────────────────────────────────

@router.put(
    "/{result_id}/correct",
    response_model=ResultCorrectionResponse,
    summary="Apply teacher corrections to a grading result",
)
async def correct_result(
    result_id: str,
    teacher_id: TeacherId,
    body: ResultCorrectionRequest,
) -> ResultCorrectionResponse:
    logger.info("Teacher %s correcting result %s", teacher_id, result_id)

    result_row = await _get_result_with_ownership(result_id, teacher_id)

    # Merge new corrections with any existing ones
    existing_corrections: dict[str, Any] = result_row.get("teacher_corrections_json") or {}
    new_corrections = {k: v.model_dump() for k, v in body.corrections.items()}
    merged_corrections = {**existing_corrections, **new_corrections}

    # Recalculate final_score:
    # Start from original total_score, then apply all corrections (delta)
    original_total = float(result_row["total_score"])
    max_score = float(result_row["max_score"])

    correction_delta = 0.0
    for _q, corr in merged_corrections.items():
        correction_delta += corr["corrected_score"] - corr["original_score"]

    final_score = round(original_total + correction_delta, 2)
    # Clamp between 0 and max_score
    final_score = max(0.0, min(final_score, max_score))

    percentage = round((final_score / max_score) * 100, 2) if max_score > 0 else 0.0

    logger.info(
        "Result %s: original=%.2f, delta=%.2f, final=%.2f / %.2f (%.1f%%)",
        result_id, original_total, correction_delta, final_score, max_score, percentage,
    )

    # Update in database
    sb = await get_supabase_client()
    try:
        update_result = (
            await sb.table("grading_results")
            .update({
                "teacher_corrections_json": merged_corrections,
                "final_score": final_score,
            })
            .eq("id", result_id)
            .execute()
        )
    except Exception as exc:
        logger.error("Failed to update result %s: %s", result_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save corrections",
        ) from exc

    if not update_result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Update returned no data",
        )

    corrections_count = len(body.corrections)
    logger.info(
        "Result %s corrected: %d question(s) updated, final_score=%.2f",
        result_id, corrections_count, final_score,
    )

    return ResultCorrectionResponse(
        id=result_id,
        exam_id=result_row["exam_id"],
        total_score=original_total,
        final_score=final_score,
        max_score=max_score,
        percentage=percentage,
        teacher_corrections_json=merged_corrections,
        message=f"{corrections_count} correction(s) applied. Final score: {final_score}/{max_score}",
    )
