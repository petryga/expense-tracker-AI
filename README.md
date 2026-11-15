# Expense Tracker — AI

A small FastAPI service that suggests a category for each card-statement row. The Expense Tracker's TypeScript API (`BE/`) calls it during statement import; the browser never does.

**One rule:** LLM work happens here, money stays in `BE/`. This service does no money math, has no user auth, and never decides anything on its own. `BE/` validates every answer and a person confirms every row.

> Status: skeleton. `POST /categorize` answers "no suggestion" for every row; the model and the eval come next (see `PLANS.md`, Plan 3, Phase B).

## API

| | |
|---|---|
| `GET /health` | `{ "status": "ok" }`, no auth |
| `POST /categorize` | `{ rows: [{ id, text, amountCents }], categories: [name] }` → `{ suggestions: [{ id, category \| null, source }] }`. `source` is `model` or `none`. |

- Requires the `X-AI-Secret` header to match `AI_SHARED_SECRET`. With the secret unset, every request is refused (503), so a misconfigured deploy fails closed.
- `X-Request-Id` from `BE/` is kept and echoed back, and goes in the log line, so one import can be traced across both services.
- Logs one line per request: method, path, status, duration, request id. Never bodies: they hold statement descriptions and amounts.
- At most 500 rows and 300 categories per call; unknown fields are rejected.

## Running locally

```bash
python3.14 -m venv .venv
.venv/bin/pip install -e '.[dev]'
cp .env.example .env   # then set AI_SHARED_SECRET (same value as BE/.env)
.venv/bin/uvicorn app.main:app --port 8000 --reload
```

## Checks

```bash
.venv/bin/ruff format --check . && .venv/bin/ruff check . && .venv/bin/mypy app tests && .venv/bin/pytest -q
```

CI runs the same. Tests use synthetic rows only.

## Data

`data/` and `results/` are gitignored. Real statements, the labelled eval set and eval outputs live there and are never committed.
