from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


# ── Request schemas ──────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=128)
    name: str = Field(..., min_length=1, max_length=255)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1)


# ── Response schemas ─────────────────────────────────────────

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TeacherResponse(BaseModel):
    id: str
    email: str
    name: str
    subscription_tier: Optional[str] = "free"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
