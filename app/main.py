import logging
import re
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import Depends, FastAPI, Request, Response

from app.auth import require_shared_secret
from app.categorizer import categorize
from app.config import get_settings
from app.schemas import CategorizeRequest, CategorizeResponse

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
def categorize_rows(body: CategorizeRequest) -> CategorizeResponse:
    return CategorizeResponse(suggestions=categorize(body.rows, body.categories))
