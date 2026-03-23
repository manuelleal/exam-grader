from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


# ── Request schemas ──────────────────────────────────────────

class ExamReviewRequest(BaseModel):
    corrections: dict[str, Optional[str]]


class ExamUpdateAnswersRequest(BaseModel):
    answers: dict[str, Any]


# ── Response schemas ─────────────────────────────────────────

class ExamResponse(BaseModel):
    id: str
    session_id: str
    student_name: Optional[str] = None
    student_id: Optional[str] = None
    image_urls: list[str] = []
    page_count: int = 1
    extracted_answers_json: Optional[dict[str, Any]] = None
    status: str = "pending"
    error_message: Optional[str] = None
    needs_review_reason: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ExamBriefResponse(BaseModel):
    id: str
    session_id: str
    student_name: Optional[str] = None
    status: str = "pending"
    score_preview: Optional[float] = None
    max_score: Optional[float] = None
    needs_review_reason: Optional[str] = None
    created_at: Optional[datetime] = None


class ExamListResponse(BaseModel):
    exams: list[ExamBriefResponse]
    count: int
