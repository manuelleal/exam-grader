from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ── Request schemas ──────────────────────────────────────────

class SessionCreate(BaseModel):
    template_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1, max_length=255)


# ── Nested helpers ───────────────────────────────────────────

class StudentExamBrief(BaseModel):
    id: str
    student_name: Optional[str] = None
    status: str
    image_urls: list[str] = []
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None


class TemplateInfo(BaseModel):
    id: str
    name: str
    subject: str
    mode: str
    max_score: float


# ── Response schemas ─────────────────────────────────────────

class SessionResponse(BaseModel):
    id: str
    template_id: str
    teacher_id: str
    name: str
    total_students: int = 0
    processed_students: int = 0
    status: str = "processing"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class SessionDetailResponse(SessionResponse):
    template: Optional[TemplateInfo] = None
    student_exams: list[StudentExamBrief] = []


class SessionListResponse(BaseModel):
    sessions: list[SessionResponse]
    count: int


class SessionUploadResponse(BaseModel):
    session_id: str
    uploaded: int
    student_exams: list[StudentExamBrief]
    message: str


class SessionProcessResponse(BaseModel):
    session_id: str
    processing_status: str
    message: str


class SessionStatusResponse(BaseModel):
    session_id: str
    status: str
    total: int = 0
    processed: int = 0
    pending: int = 0
    failed: int = 0
    current_processing: Optional[str] = None
    progress_percentage: int = 0
    estimated_time_remaining: Optional[int] = None
    errors: list[dict] = []
