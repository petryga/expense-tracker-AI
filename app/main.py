import logging
import re
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, Response

from app.auth import require_shared_secret
from app.categorizer import categorize_with_report
from app.config import Settings, get_settings
from app.examples_store import StoredExample, sync
from app.retrieval import default_embedder, examples_for
from app.schemas import (
    CategorizeRequest,
    CategorizeResponse,
    SyncExamplesRequest,
    SyncExamplesResponse,
)

logging.basicConfig(
    level=get_settings().log_level,
    format='{"level":"%(levelname)s","msg":"%(message)s"}',
)
log = logging.getLogger("ai")

app = FastAPI(title="Expense Tracker AI", docs_url=None, redoc_url=None, openapi_url=None)

# Same rule as BE/: keep a caller's id only if it looks like one.
REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


@app.middleware("http")
async def request_id_and_log(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """One log line per request with the id BE/ passed on. Never bodies:
    they hold statement descriptions and amounts."""
    incoming = request.headers.get("x-request-id", "")
    request_id = incoming if REQUEST_ID.match(incoming) else str(uuid.uuid4())
    start = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Request-Id"] = request_id
    log.info(
        "%s %s %s %dms id=%s",
        request.method,
        request.url.path,
        response.status_code,
        (time.perf_counter() - start) * 1000,
        request_id,
    )
    return response


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/categorize", dependencies=[Depends(require_shared_secret)])
def categorize_rows(
    body: CategorizeRequest, settings: Annotated[Settings, Depends(get_settings)]
) -> CategorizeResponse:
    # Settings come through the dependency, like the secret check, so one
    # configuration governs the whole request (and tests can replace it).
    user_id = str(body.user_id) if body.user_id else None
    examples = examples_for(body.rows, body.categories, user_id, settings)
    suggestions, _ = categorize_with_report(body.rows, body.categories, settings, examples)
    return CategorizeResponse(suggestions=suggestions)


@app.put("/examples", dependencies=[Depends(require_shared_secret)])
def sync_examples(
    body: SyncExamplesRequest, settings: Annotated[Settings, Depends(get_settings)]
) -> SyncExamplesResponse:
    """BE/ sends every past item choice of a user before asking for item
    suggestions; the stored set is made to match, so edits and deletions in
    the app are picked up without separate calls."""
    if not settings.ai_database_url:
        raise HTTPException(status_code=503, detail="retrieval is not configured")
    wanted = [StoredExample(e.source, e.text, e.category) for e in body.examples]
    user_id = str(body.user_id) if body.user_id else None
    try:
        result = sync(settings.ai_database_url, user_id, "item", wanted, default_embedder())
    except Exception as error:
        # The error may quote product names; log its type only.
        log.warning("examples sync failed: %s", type(error).__name__)
        raise HTTPException(status_code=503, detail="examples store unavailable") from None
    return SyncExamplesResponse(
        stored=result.stored, embedded=result.embedded, removed=result.removed
    )
