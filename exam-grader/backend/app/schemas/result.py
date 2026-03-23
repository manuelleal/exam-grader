from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ── Response schemas ─────────────────────────────────────────

class ResultResponse(BaseModel):
    id: str
    exam_id: str
    total_score: float
    max_score: float
    percentage: Optional[float] = None
    section_scores_json: Optional[dict[str, Any]] = None
    feedback_json: Optional[dict[str, Any]] = None
    teacher_corrections_json: Optional[dict[str, Any]] = None
    final_score: Optional[float] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ── Request schemas ──────────────────────────────────────────

class CorrectionItem(BaseModel):
    original_score: float = Field(..., ge=0)
    corrected_score: float = Field(..., ge=0)
    reason: str = Field(..., min_length=1, max_length=500)


class ResultCorrectionRequest(BaseModel):
    corrections: dict[str, CorrectionItem] = Field(
        ...,
        min_length=1,
        description="Map of question number to correction details",
    )


class ResultCorrectionResponse(BaseModel):
    id: str
    exam_id: str
    total_score: float
    final_score: float
    max_score: float
    percentage: Optional[float] = None
    teacher_corrections_json: dict[str, Any]
    message: str
