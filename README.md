# Expense Tracker — AI

A small FastAPI service that suggests a category for each card-statement row. The Expense Tracker's TypeScript API (`BE/`) calls it during statement import; the browser never does.

**One rule:** LLM work happens here, money stays in `BE/`. This service does no money math, has no user auth, and never decides anything on its own. `BE/` validates every answer and a person confirms every row.

> Status: working. Backends: `none` (default, no suggestions), `ollama` (a local model) and `claude` (Claude Haiku 5.5 by default), chosen with `AI_BACKEND`. Eval results below.

## API

| | |
|---|---|
| `GET /health` | `{ "status": "ok" }`, no auth |
| `POST /categorize` | `{ rows: [{ id, text, amountCents, bankCategory?, kind? }], categories: [name], userId? }` → `{ suggestions: [{ id, category \| null, source }] }`. `source` is `model` or `none`. A row with `kind: "item"` is an order item (the text is a product name) and is shown that user's past choices for similar products. |
| `POST /ask` | `{ question, history?: [{ role, text }], userToken? }` → `{ answer, outcome, toolCalls }`. The spending assistant; see below. `outcome` is `answered`, or why it stopped: `max_steps`, `timeout`, `model_error`. |
| `PUT /examples` | `{ userId?, examples: [{ source, text, category }] }`: every past item choice of the user. The stored set is made to match; only new or reworded ones are embedded. → `{ stored, embedded, removed }` |

- Requires the `X-AI-Secret` header to match `AI_SHARED_SECRET`. With the secret unset, every request is refused (503), so a misconfigured deploy fails closed.
- `X-Request-Id` from `BE/` is kept and echoed back, and goes in the log line, so one import can be traced across both services.
- Logs one line per request: method, path, status, duration, request id. Never bodies: they hold statement descriptions and amounts.
- At most 500 rows and 300 categories per call; unknown fields are rejected. The service asks the model in chunks of 40 rows, so a long statement can't run past the model's output limit, and one failed chunk costs only its own rows.

## Spending assistant

`POST /ask` answers a question about the user's own spending. It is a tool-calling loop (`app/agent/`): Claude gets the question, the earlier turns and the read-only tools of the Expense Tracker MCP server (the `MCP/` repo), asks for tool calls, gets their results, and answers.

- **Tools come from the MCP server**, started as a subprocess over stdio for each question with the asking user's token, so it can read only that user's data. Only tools the server marks read-only are offered; a call to anything else is refused here.
- **Guardrails:** at most 6 model calls and 60 s per question, then a fixed message. A cut-off, refused or empty reply, or an API error, becomes "unavailable" rather than a half answer. Questions outside the data get "I can't answer that from your data."
- **The prompt** keeps CAD and USD apart, requires every number to come from a tool result, asks for plain text, and forbids claiming checks that weren't made for the current question. (An early version said it had "re-checked" figures it never looked at; earlier turns carry only text, not the tools behind them.)
- **Logs** hold the outcome, tool names, call count, tokens and time; never the question or the answer.
- Measured on invented data with Haiku 5.5: 1–4 s and about $0.0005 a question (about 4,000 tokens in, 250 out, over 1–3 model calls).

### Assistant eval

```bash
.venv/bin/python -m eval.assistant --claude claude-haiku-5-5 --runs 3
```

12 questions with known answers, on invented data (`eval/assistant_data.py`) served by a small fake API (`eval/fake_api.py`). The real agent loop and the real MCP server (`../MCP/dist/index.js`, built) do the work. The correct figures are computed from the same rows the fake API serves. Grading is automatic and strict: every expected number must appear, at least one word from each word group, and no forbidden number (for example CAD and USD added together, or another month's total borrowed for a month with no data).

The questions cover a relative date ("last month"), top category, a two-month comparison, a three-month series, counting, recurring totals, the biggest single purchase, a budget check, CAD-only spending, an off-topic question (must refuse with the fixed phrase), a write request (must point to the app, never claim it added anything) and a month with no data.

| Run (2026-11-17, Haiku 5.5) | Passed | Model calls | Cost |
|---|---|---|---|
| 1 | 12/12 | 23 | $0.0061 |
| 2 | 12/12 | 23 | $0.0062 |
| 3 | 12/12 | 23 | $0.0062 |

As first graded, runs 1 and 2 scored 11/12: the budget answer said "No, you weren't over… 16.65 USD against a budget of 30", which is right, but the grader's word list lacked "weren't over". The word list was widened and the saved answers re-graded; no answer changed. Each question used the same tools in all three runs. One thing the eval surfaced about the app itself: category budgets have no currency, and the assistant said so rather than assume one. (Left as it is: budgets are in the one currency the owner now uses.)

Needs `AI_BACKEND=claude`, the MCP server built (`npm run build` in `MCP/`) and `node` on the PATH. Settings: `MCP_SERVER_COMMAND`, `MCP_SERVER_ARGS`, `EXPENSE_TRACKER_API_URL`, `AI_AGENT_MODEL` (see `.env.example`). `BE/` exposes it as `POST /assistant`.

## Retrieval of past choices

An order item's product name rarely says how its owner files it (is a notebook Education or a hobby?). So before asking the model, the service looks up the user's most similar past items and shows them next to the row. On labelled items this beat both no examples and random examples (see "Order items" under Results).

- **Embeddings** come from a small local model (`BAAI/bge-small-en-v1.5` through `fastembed`), so product names are not sent to a second provider and there is no second key.
- **Storage** is one Postgres table with pgvector, `category_examples`, created by a `BE/` migration. This service is the only reader and writer, through a role that can use that table and nothing else. Lookup is an exact nearest-neighbour scan filtered by user: a user has a few thousand rows at most.
- **The table is an index, not a source of truth.** `BE/` sends the user's full current set (`PUT /examples`) before it asks about items, so a category edited or an expense deleted in the app is reflected without separate calls.
- **Only order items get examples.** Statement rows are asked in a separate model call with exactly the prompt they had before; repeat merchants are already covered by merchant memory in `BE/`.
- **It is optional.** With no `AI_DATABASE_URL`, no table, or no embedding model installed, rows are categorized without examples.

Setup, once (the role has no access to anything else):

```sql
CREATE ROLE expense_tracker_ai LOGIN;  -- add a password anywhere but a local trust setup
GRANT CONNECT ON DATABASE expense_tracker TO expense_tracker_ai;
GRANT USAGE ON SCHEMA public TO expense_tracker_ai;
GRANT SELECT, INSERT, UPDATE, DELETE ON category_examples TO expense_tracker_ai;
```

Then `pip install -e '.[embeddings]'` and set `AI_DATABASE_URL` in `.env` (see `.env.example`).

## Running locally

```bash
python3.14 -m venv .venv
.venv/bin/pip install -e '.[dev]'
cp .env.example .env   # then set AI_SHARED_SECRET (same value as BE/.env)
.venv/bin/uvicorn app.main:app --port 8000 --reload
```

## Checks

```bash
.venv/bin/ruff format --check . && .venv/bin/ruff check . && .venv/bin/mypy app eval tests && .venv/bin/pytest -q
```

CI runs the same. Tests use synthetic rows only. The examples-store tests need a Postgres with pgvector: set `AI_TEST_DATABASE_URL` to a throwaway database (CI has one); they are skipped without it.

## Labelling the eval set

The eval needs the right category for each of your non-Amazon card charges (Amazon rows are matched to orders instead, in Phase D). Everything stays in `data/`, on this machine.

```bash
./scripts/export_local_data.sh ~/path/to/statements  # CSVs + your expenses and categories -> data/
.venv/bin/python -m eval.prepare_labels # -> data/labels.csv, one row per charge
.venv/bin/python -m eval.check_labels   # progress per month, and any bad labels
```

In `data/labels.csv`:

- `guess` is a starting point, never a model's answer. It comes from your own hand-entered expense on that card (set `EVAL_CARD_ACCOUNT` to the card's account name in the app) with the same amount within 4 days (`guess_from` says which), or is `can't tell` for marketplaces (Poshmark, Vinted, eBay, Walmart…) whose rows don't say what was bought. Conflicting or missing matches are left blank.
- Put the right category in `label` (one of `data/categories.csv`, or `can't tell`), then `y` in `checked`. Only checked rows count. `note` is free text.
- Open it in Numbers or Excel; from Numbers, save back with File > Export To > CSV over the same file. Don't upload it anywhere online.
- Re-running `prepare_labels` keeps every label and check you've made.

## Eval

```bash
.venv/bin/python -m eval.run                       # all predictors
.venv/bin/python -m eval.run memory --misses memory
```

Every month from August 2025 on is a test month, answered using only the months before it (the set is small, so every month counts; earlier months are history only). Rows labelled `can't tell` (general marketplaces: eBay, AliExpress, Shein, Vinted, Walmart, Etsy) are right only when the predictor suggests nothing. Results also go to `results/` (gitignored).

- **accuracy**: right suggestions over all rows that have a category
- **precision**: right over all suggestions made on those rows
- **held back**: share of can't-tell rows with no suggestion

Merchant memory uses `eval/merchant.py` to normalize merchants (prefixes and store numbers stripped, first two words). It is reimplemented here for the eval; `BE/` uses the same rule in the app, and a test there checks the two agree.

### Prompt freeze

The categorization prompt (`app/prompt.py`: system prompt, examples note, row layout, answer schema) is **frozen as of 2026-11-17** (`PROMPT_FROZEN_ON`). The accuracy figures below come from the same rows the prompt was adjusted on, so they flatter it. Accuracy on rows imported after the freeze date is held out: the prompt never saw them while being written. `tests/test_prompt_freeze.py` fails on any change to the prompt, so a change can't slip in unnoticed; an intended change starts a new freeze date, and numbers from before it no longer describe the prompt.

The held-out number comes from real use, not a labelled set: `BE/` records what was suggested for every purchase saved on review, and `npx tsx scripts/suggestion-report.ts` (in `BE/`) compares it with the category the expense has now, per month and per source (merchant memory or model), with a 95% range next to every percentage.

| Freeze | Changes |
|---|---|
| 2026-11-17 | First freeze. |

### Results

**Current (2026-11-15):** 206 non-Amazon card charges, January 2025 to November 2026. Test months 2025-08 on: 150 rows with a category, 45 can't tell. Every row is scored: the gift labels were relabelled with each item's real category once gifts became a checkbox in the app.

| Predictor | Accuracy | Precision | Held back on can't tell |
|---|---|---|---|
| Merchant memory | 44.0% (66/150) | 95.7% (66/69) | 100% (45/45) |
| Bank's category → your category | 51.3% (77/150) | 70.0% (77/110) | 75.6% (34/45) |
| Memory, then bank-category mapping | 60.0% (90/150) | 78.3% (90/115) | 88.9% (40/45) |
| **Memory, then Claude Haiku 5.5** | **76.0% (114/150)** | **91.2% (114/125)** | **97.8% (44/45)** |

**Run to run (2026-11-17, three runs, same prompt and data):** memory then Haiku scored 113, 115 and 114 of 150 (75.3–76.7%, mean 76.0%), held back on 44–45 of 45 can't-tell rows, about $0.006 a run. Haiku alone varied more: 92, 87 and 88 (58.0–61.3%). The rules-only rows don't change between runs. So a single run of the main setup is good to about ±1 row; differences of a few rows between single runs, as in the older tables below, are within noise.

Memory then Haiku: 15 calls, 41 s, $0.0058, 0 failed calls, 0 invalid answers. It beats the best rules-only row (memory, then bank-category mapping) by 16 points, with higher precision and fewer guesses on can't-tell rows. On 150 rows a single run is good to roughly plus or minus 7 points. The tables below are earlier runs, kept for the model and effort comparisons; each was measured on the label set of its day (143 rows with 7 gift rows left out), so compare within a table, not across.

**Earlier, 143 rows (gift rows left out):**

| Predictor | Accuracy | Precision | Held back on can't tell |
|---|---|---|---|
| Merchant memory | 44.1% (63/143) | 95.5% (63/66) | 100% (45/45) |
| Bank's category → your category (learned from earlier months) | 51.7% (74/143) | 70.5% (74/105) | 77.8% (35/45) |
| Memory, then bank-category mapping | 60.1% (86/143) | 78.9% (86/109) | 88.9% (40/45) |
| Claude Haiku 5.5 alone | 59.4% (85/143) | 75.9% (85/112) | 93.3% (42/45) |
| **Memory, then Claude Haiku 5.5** | **77.6% (111/143)** | **88.1% (111/126)** | **100% (45/45)** |
| Claude Sonnet 5.5 alone | 65.0% (93/143) | 84.5% (93/110) | 97.8% (44/45) |
| Memory, then Claude Sonnet 5.5 | 79.0% (113/143) | 90.4% (113/125) | 100% (45/45) |

Claude Haiku 5.5 run (2026-11-15): `claude-haiku-5-5`, effort `low`, answers constrained by JSON schema (structured outputs) to the category list or null, one call per test month. 0 failed calls, 0 invalid answers. Memory then Haiku: 15 calls, 24k tokens in / 5k out, 33 s in total, **$0.0047**. Haiku alone: 16 calls, $0.0082. Of its 32 misses, 17 are no suggestion rather than a wrong one: it leaves rows blank more often than it guesses.

Claude Sonnet 5.5 run (same day, same prompt, schema and effort `low`): memory then Sonnet 79.0% (113/143), 2 rows more than Haiku, at 90.4% precision; 15 calls, 36 s, **$0.068** (14x Haiku's $0.0047). Sonnet alone: $0.108. One run each, so a 2-row difference is within noise; Haiku is the better value for this task.

Effort on Haiku (memory then Haiku, one run each):

| Effort | Accuracy | Precision | Held back | Output tokens | Time | Cost |
|---|---|---|---|---|---|---|
| **low** | **77.6% (111/143)** | 88.1% | 100% (45/45) | 4.7k | 33 s | $0.0047 |
| medium | 74.8% (107/143) | 90.7% | 97.8% (44/45) | 7.4k | 42 s | $0.0061 |
| high | 74.8% (107/143) | 89.9% | 97.8% (44/45) | 9.6k | 55 s | $0.0072 |

More thinking made it slightly more cautious and no more accurate, and it guessed once on a can't-tell row. `low` stays the default (`AI_EFFORT`).

The model has to beat the memory-then-bank-category row: memory then Haiku does, by 17.5 points, with higher precision and no guesses on can't-tell rows. Labels were pre-filled from hand-entered expenses and then confirmed by hand, never by a model.

**Earlier run, before Gifts were left out** (150 category rows; not directly comparable to the table above):

| Predictor | Accuracy | Precision | Held back on can't tell |
|---|---|---|---|
| Memory, then bank-category mapping | 56.7% (85/150) | 73.9% (85/115) | 88.9% (40/45) |
| Local model alone (27B open-weights model, Ollama) | 64.0% (96/150) | 69.1% (96/139) | 71.1% (32/45) |
| Memory, then local model | 71.3% (107/150) | 74.8% (107/143) | 93.3% (42/45) |

Local model run (2026-11-15, Apple Silicon laptop, 48 GB): a quantized 27B open-weights model served by Ollama, temperature 0, answers constrained to the category list or null by JSON schema. One call per test month: 0 failed calls, 0 invalid answers. Model alone: 16 calls, 20k tokens in / 8k out, 18 min. After memory: 15 calls, 12k in / 4k out, 9 min. No cost; nothing left the machine. It was the first data point, before the Claude runs above.

Main kinds of misses (memory then model, 43 rows): purchases whose category depends on why they were bought, which the statement can't show (the reason a gift is now a checkbox you tick, not a category); foreign merchants whose names are transliterated and say little; a resale marketplace missing from the prompt's list of "can't tell" shops; a shop labelled two ways in history, so memory picked the other; and near-neighbour categories confused (e.g. Beauty vs Wellness & Spa).

### Order items, and whether showing past choices helps

`python -m eval.items --claude MODEL --examples 3` scores the category suggested for an
order item from its product name alone, in three arms: no examples, 3 random past
choices, and 3 past choices retrieved by similarity (a small local embedding model,
`pip install -e '.[embeddings]'`; nothing leaves the machine for that step).

An item is only shown items from earlier months, and each month is asked in its own
call. Asking everything at once leaks answers: an item's label appears in the same
prompt as another item's past choice. A first version did that, and random examples
scored 91%.

80 labelled items, Haiku 5.5 at low effort, three runs each (items right out of 80):

| Arm | Run 1 | Run 2 | Run 3 | Mean |
|---|---|---|---|---|
| Always the most common category | 19 | 19 | 19 | 23.8% |
| No examples | 59 | 54 | 57 | 70.8% |
| 3 random past choices | 61 | 61 | 59 | 75.4% |
| 3 retrieved past choices | 67 | 64 | 67 | 82.5% |

Retrieved examples won in every run, by about 12 points over no examples and 7 over
random ones. The set is small, so treat that as a direction and a rough size, not a
precise figure. Most of the gain is the owner's own conventions between near
categories, which a product name alone can't tell the model.

## Data

`data/` and `results/` are gitignored. Real statements, the labelled eval set and eval outputs live there and are never committed.
