from typing import Annotated

from fastapi import Header, HTTPException, status

from monitor.settings import Settings


def get_settings() -> Settings:
    return Settings()


def require_api_key(
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> None:
    """Validate the admin API key for mutating requests."""
    expected_key = get_settings().api_key
    if x_api_key is None or x_api_key != expected_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-API-Key header",
        )
