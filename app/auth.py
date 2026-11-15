import hmac
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from app.config import Settings, get_settings


def require_shared_secret(
    settings: Annotated[Settings, Depends(get_settings)],
    x_ai_secret: Annotated[str | None, Header()] = None,
) -> None:
    """Only BE/ may call this service. It is never called from the browser."""
    if not settings.ai_shared_secret:
        # Fail closed: a deploy without the secret must not serve requests.
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Service is not configured")
    if not x_ai_secret or not hmac.compare_digest(x_ai_secret, settings.ai_shared_secret):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unauthorized")
