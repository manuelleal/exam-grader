from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRouter

from app.core.config import get_settings
from app.core.database import close_supabase_client, get_supabase_client


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Supabase client is initialized lazily on first use;
    # no need to block startup. Clean up on shutdown if created.
    yield
    await close_supabase_client()


settings = get_settings()

app = FastAPI(
    title="Exam Grader API",
    description="AI-powered exam grading system",
    version="0.1.0",
    debug=settings.DEBUG,
    lifespan=lifespan,
)

_cors_origins = ["*"] if settings.is_development else settings.cors_origins_list

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False if "*" in _cors_origins else True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["health"])
async def health_check() -> dict[str, str]:
    return {"status": "ok", "environment": settings.ENVIRONMENT}


# ── API v1 router ────────────────────────────────────────────
from app.api.v1 import auth, exams, results, sessions, templates  # noqa: E402

api_v1 = APIRouter(prefix="/api/v1")
api_v1.include_router(auth.router, prefix="/auth", tags=["auth"])
api_v1.include_router(templates.router, prefix="/templates", tags=["templates"])
api_v1.include_router(sessions.router, prefix="/sessions", tags=["sessions"])
api_v1.include_router(exams.router, prefix="/exams", tags=["exams"])
api_v1.include_router(results.router, prefix="/results", tags=["results"])
app.include_router(api_v1)


if __name__ == "__main__":
    import os
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
