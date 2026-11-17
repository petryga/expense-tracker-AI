import logging
import re
import shlex
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Annotated, cast

from fastapi import Depends, FastAPI, HTTPException, Request, Response

from app.agent.loop import Model, Turn, answer_question
from app.agent.mcp_tools import mcp_toolbox
from app.auth import require_shared_secret
from app.categorizer import categorize_with_report
from app.config import Settings, get_settings
from app.examples_store import StoredExample, sync
from app.retrieval import default_embedder, examples_for
from app.schemas import (
    AskRequest,
    AskResponse,
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


def _model(settings: Settings) -> Model:
    """The Anthropic Messages API (a seam for tests)."""
    import anthropic

    client = anthropic.Anthropic(
        api_key=settings.anthropic_api_key, timeout=settings.ai_timeout_s, max_retries=2
    )
    # Messages.create is overloaded (streaming or not); the loop uses the plain form.
    return cast(Model, client.messages)


@app.post("/ask", dependencies=[Depends(require_shared_secret)])
async def ask(
    body: AskRequest, settings: Annotated[Settings, Depends(get_settings)]
) -> AskResponse:
    """The spending assistant: answers a question about the user's own data
    by calling the read-only tools of the Expense Tracker MCP server."""
    if settings.ai_backend != "claude" or not settings.anthropic_api_key:
        raise HTTPException(status_code=503, detail="the assistant is not configured")
    model_name = settings.ai_agent_model or settings.ai_model or "claude-haiku-5-5"
    history = [Turn(t.role, t.text) for t in body.history]
    try:
        async with mcp_toolbox(
            settings.mcp_server_command,
            shlex.split(settings.mcp_server_args),
            settings.expense_tracker_api_url,
            body.user_token,
        ) as toolbox:
            result = await answer_question(
                body.question,
                history,
                toolbox,
                _model(settings),
                model_name,
            )
    except Exception as error:
        # The MCP server could not start or broke off. Type only: no content in logs.
        log.warning("assistant unavailable: %s", type(error).__name__)
        raise HTTPException(status_code=503, detail="the assistant is unavailable") from None
    # Counts and timing only; never the question or the answer.
    log.info(
        "ask outcome=%s tools=%s model_calls=%d tokens_in=%d tokens_out=%d %.1fs",
        result.outcome,
        ",".join(result.tool_calls) or "-",
        result.model_calls,
        result.input_tokens,
        result.output_tokens,
        result.seconds,
    )
    return AskResponse(answer=result.answer, outcome=result.outcome, tool_calls=result.tool_calls)
