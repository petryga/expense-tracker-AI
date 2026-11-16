# Expense Tracker — AI

A small FastAPI service that suggests a category for each card-statement row. The Expense Tracker's TypeScript API (`BE/`) calls it during statement import; the browser never does.

**One rule:** LLM work happens here, money stays in `BE/`. This service does no money math, has no user auth, and never decides anything on its own. `BE/` validates every answer and a person confirms every row.

> Status: working. Backends: `none` (default, no suggestions), `ollama` (a local model) and `claude` (Claude Haiku 5.5 by default), chosen with `AI_BACKEND`. Eval results below.

## API

| | |
|---|---|
| `GET /health` | `{ "status": "ok" }`, no auth |
| `POST /categorize` | `{ rows: [{ id, text, amountCents, bankCategory? }], categories: [name] }` → `{ suggestions: [{ id, category \| null, source }] }`. `source` is `model` or `none`. |

- Requires the `X-AI-Secret` header to match `AI_SHARED_SECRET`. With the secret unset, every request is refused (503), so a misconfigured deploy fails closed.
- `X-Request-Id` from `BE/` is kept and echoed back, and goes in the log line, so one import can be traced across both services.
- Logs one line per request: method, path, status, duration, request id. Never bodies: they hold statement descriptions and amounts.
- At most 500 rows and 300 categories per call; unknown fields are rejected. The service asks the model in chunks of 40 rows, so a long statement can't run past the model's output limit, and one failed chunk costs only its own rows.

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

CI runs the same. Tests use synthetic rows only.

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

Merchant memory uses `eval/merchant.py` to normalize merchants (prefixes and store numbers stripped, first two words). It is reimplemented here for the eval; when it moves into `BE/`, it must use the same rule.

### Results

**Current (2026-11-15):** 206 non-Amazon card charges, January 2025 to November 2026. Test months 2025-08 on: 150 rows with a category, 45 can't tell. Every row is scored: the gift labels were relabelled with each item's real category once gifts became a checkbox in the app.

| Predictor | Accuracy | Precision | Held back on can't tell |
|---|---|---|---|
| Merchant memory | 44.0% (66/150) | 95.7% (66/69) | 100% (45/45) |
| Bank's category → your category | 51.3% (77/150) | 70.0% (77/110) | 75.6% (34/45) |
| Memory, then bank-category mapping | 60.0% (90/150) | 78.3% (90/115) | 88.9% (40/45) |
| **Memory, then Claude Haiku 5.5** | **76.0% (114/150)** | **91.2% (114/125)** | **97.8% (44/45)** |

Memory then Haiku: 15 calls, 41 s, $0.0058, 0 failed calls, 0 invalid answers. The tables below are earlier runs, kept for the model and effort comparisons; each was measured on the label set of its day (143 rows with 7 gift rows left out), so compare within a table, not across.

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
| Local model alone (Qwen 27B fine-tune, Ollama) | 64.0% (96/150) | 69.1% (96/139) | 71.1% (32/45) |
| Memory, then local model | 71.3% (107/150) | 74.8% (107/143) | 93.3% (42/45) |

Local model run (2026-11-15, Apple Silicon laptop, 48 GB): `hf.co/JonathanColetti/Qwen3.8-27B-Uncensored-GGUF:Q5_K_M`, temperature 0, answers constrained to the category list or null by JSON schema. One call per test month: 0 failed calls, 0 invalid answers. Model alone: 16 calls, 20k tokens in / 8k out, 18 min. After memory: 15 calls, 12k in / 4k out, 9 min. No cost; nothing left the machine. It is a community fine-tune, not a mainstream release, so treat it as a first data point; Claude (decision 10) is still to run.

Main kinds of misses (memory then model, 43 rows): purchases whose category depends on why they were bought, which the statement can't show (the reason a gift is now a checkbox you tick, not a category); foreign merchants whose names are transliterated and say little; a resale marketplace missing from the prompt's list of "can't tell" shops; a shop labelled two ways in history, so memory picked the other; and near-neighbour categories confused (e.g. Beauty vs Wellness & Spa).

The model has to beat the memory-then-bank-category row: memory then Haiku does, by 17.5 points, with higher precision and no guesses on can't-tell rows. Labels were pre-filled from hand-entered expenses and then confirmed by hand, never by a model.

## Data

`data/` and `results/` are gitignored. Real statements, the labelled eval set and eval outputs live there and are never committed.
