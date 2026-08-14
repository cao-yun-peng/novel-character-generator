from hmac import compare_digest
from typing import Annotated, Literal

from fastapi import Header, HTTPException, status

from novel_character_generator.settings import get_settings

Principal = Literal["development", "user", "admin"]


def _matches(candidate: str | None, expected: str | None) -> bool:
    return candidate is not None and expected is not None and compare_digest(candidate, expected)


def _configured_keys() -> tuple[str | None, str | None]:
    settings = get_settings()
    user_key = settings.user_api_key.get_secret_value() if settings.user_api_key else None
    admin_key = settings.admin_api_key.get_secret_value() if settings.admin_api_key else None
    return user_key, admin_key


async def require_user_api_key(
    api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> Principal:
    settings = get_settings()
    user_key, admin_key = _configured_keys()
    if settings.app_env != "production" and user_key is None and admin_key is None:
        return "development"
    if _matches(api_key, admin_key):
        return "admin"
    if _matches(api_key, user_key):
        return "user"
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="invalid_api_key",
        headers={"WWW-Authenticate": "ApiKey"},
    )


async def require_admin_api_key(
    api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> Principal:
    settings = get_settings()
    user_key, admin_key = _configured_keys()
    if settings.app_env != "production" and user_key is None and admin_key is None:
        return "development"
    if _matches(api_key, admin_key):
        return "admin"
    if _matches(api_key, user_key):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin_api_key_required")
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="invalid_api_key",
        headers={"WWW-Authenticate": "ApiKey"},
    )
