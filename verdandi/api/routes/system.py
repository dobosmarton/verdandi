"""Health check and config endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from verdandi.api.deps import DbDep, SettingsDep
from verdandi.api.schemas import ConfigCheckResponse, HealthResponse

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
def health_check(
    db: DbDep,
) -> HealthResponse:
    db_ok = False
    try:
        db.check_connection()
        db_ok = True
    except Exception:
        pass

    return HealthResponse(
        status="healthy" if db_ok else "unhealthy",
        version="0.1.0",
        db_connected=db_ok,
    )


@router.get("/config/check", response_model=ConfigCheckResponse)
def config_check(
    settings: SettingsDep,
) -> ConfigCheckResponse:
    return ConfigCheckResponse(
        configured={
            "anthropic": bool(settings.anthropic_api_key),
            "tavily": bool(settings.tavily_api_key),
            "serper": bool(settings.serper_api_key),
            "exa": bool(settings.exa_api_key),
            "perplexity": bool(settings.perplexity_api_key),
            "porkbun": bool(settings.porkbun_api_key),
            "cloudflare": bool(settings.cloudflare_api_token),
            "umami": bool(settings.umami_api_key),
            "emailoctopus": bool(settings.emailoctopus_api_key),
            "twitter": bool(settings.twitter_bearer_token),
            "linkedin": bool(settings.linkedin_access_token),
            "reddit": bool(settings.reddit_client_id),
            "bluesky": bool(settings.bluesky_handle),
        }
    )
