from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ── Request schemas ──────────────────────────────────────────

class TemplateCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    subject: str = Field(..., min_length=1, max_length=100)
    mode: str = Field(..., pattern=r"^(integrated|separate_answer_sheet)$")
    max_score: float = Field(..., gt=0)


class AnswerKeyUpdate(BaseModel):
    answer_key: dict[str, Any] = Field(..., min_length=1)
    method: str = Field(
        default="manual",
        pattern=r"^(manual|auto_extract|excel)$",
    )


# ── Nested response helpers ──────────────────────────────────

class PartSchema(BaseModel):
    name: str
    questions: list[str]
    type: str
    options: Optional[list[str]] = None
    points_each: float


class SectionSchema(BaseModel):
    name: str
    total_points: float
    parts: list[PartSchema]


class StructureSchema(BaseModel):
    name: Optional[str] = None
    subject: Optional[str] = None
    max_score: Optional[float] = None
    sections: list[SectionSchema]


# ── Response schemas ─────────────────────────────────────────

class TemplateResponse(BaseModel):
    id: str
    teacher_id: str
    name: str
    subject: str
    mode: str
    max_score: float
    template_image_url: Optional[str] = None
    question_book_url: Optional[str] = None
    answer_sheet_template_url: Optional[str] = None
    structure_json: Optional[dict[str, Any]] = None
    answer_key_json: Optional[dict[str, Any]] = None
    answer_key_method: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class TemplateListResponse(BaseModel):
    templates: list[TemplateResponse]
    count: int


class TemplateUploadResponse(BaseModel):
    id: str
    file_type: str
    url_field: str
    image_url: str
    message: str


class StructureUpdate(BaseModel):
    structure: dict[str, Any]


class TemplateExtractResponse(BaseModel):
    id: str
    structure: dict[str, Any]
    message: str
    extraction_status: str = "complete"
    missing_points: float = 0.0
