from typing import Optional

from supabase import AsyncClient, acreate_client

from app.core.config import get_settings

_supabase_client: Optional[AsyncClient] = None


async def get_supabase_client() -> AsyncClient:
    global _supabase_client

    if _supabase_client is not None:
        return _supabase_client

    settings = get_settings()

    try:
        _supabase_client = await acreate_client(
            supabase_url=settings.SUPABASE_URL,
            supabase_key=settings.SUPABASE_KEY,
        )
    except Exception as exc:
        raise RuntimeError(
            f"Failed to initialize Supabase client: {exc}"
        ) from exc

    return _supabase_client


async def close_supabase_client() -> None:
    global _supabase_client

    if _supabase_client is not None:
        # supabase-py >=2.x may not expose aclose(); guard gracefully
        close = getattr(_supabase_client, "aclose", None)
        if callable(close):
            await close()
        _supabase_client = None
