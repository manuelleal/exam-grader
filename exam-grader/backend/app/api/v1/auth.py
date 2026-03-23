import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.database import get_supabase_client
from app.core.security import (
    create_access_token,
    get_current_teacher_id,
    hash_password,
    verify_password,
)
from app.schemas.auth import (
    LoginRequest,
    RegisterRequest,
    TeacherResponse,
    TokenResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()

TeacherId = Annotated[str, Depends(get_current_teacher_id)]


# ── Helpers ──────────────────────────────────────────────────

def _row_to_teacher(row: dict[str, Any]) -> TeacherResponse:
    """Convert a Supabase row to TeacherResponse (never exposes password_hash)."""
    return TeacherResponse(
        id=row["id"],
        email=row["email"],
        name=row["name"],
        subscription_tier=row.get("subscription_tier", "free"),
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )


# ── POST /auth/register ─────────────────────────────────────

@router.post(
    "/register",
    response_model=TeacherResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new teacher account",
)
async def register(body: RegisterRequest) -> TeacherResponse:
    sb = await get_supabase_client()

    # Check if email already exists
    existing = (
        await sb.table("teachers")
        .select("id")
        .eq("email", body.email)
        .limit(1)
        .execute()
    )
    if existing.data:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A teacher with this email already exists",
        )

    password_hash = hash_password(body.password)

    row = {
        "email": body.email,
        "name": body.name,
        "password_hash": password_hash,
    }

    try:
        result = await sb.table("teachers").insert(row).execute()
    except Exception as exc:
        logger.error("Failed to create teacher: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create teacher account",
        ) from exc

    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Insert returned no data",
        )

    logger.info("Teacher registered: %s (%s)", body.name, body.email)
    return _row_to_teacher(result.data[0])


# ── POST /auth/login ────────────────────────────────────────

@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login and receive a JWT token",
)
async def login(body: LoginRequest) -> TokenResponse:
    sb = await get_supabase_client()

    result = (
        await sb.table("teachers")
        .select("*")
        .eq("email", body.email)
        .limit(1)
        .execute()
    )

    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    teacher = result.data[0]

    if not verify_password(body.password, teacher["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    token = create_access_token(teacher["id"])
    logger.info("Teacher logged in: %s", body.email)

    return TokenResponse(access_token=token)


# ── GET /auth/me ─────────────────────────────────────────────

@router.get(
    "/me",
    response_model=TeacherResponse,
    summary="Get current teacher profile",
)
async def get_me(teacher_id: TeacherId) -> TeacherResponse:
    sb = await get_supabase_client()

    result = (
        await sb.table("teachers")
        .select("*")
        .eq("id", teacher_id)
        .limit(1)
        .execute()
    )

    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Teacher not found",
        )

    return _row_to_teacher(result.data[0])
