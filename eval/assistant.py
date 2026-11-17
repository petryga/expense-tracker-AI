"""Spending assistant eval (PLANS.md, Plan 2, Part 2).

    .venv/bin/python -m eval.assistant --claude claude-haiku-5-5 [--runs 3] [--yes]

Each question goes through the real agent loop (app/agent/) and the real MCP
server (../MCP/dist/index.js, built), which reads from a fake API serving the
invented data in eval/assistant_data.py. Answers are graded automatically
(eval/assistant_questions.py). Paid: questions go to the Anthropic API. The
data is invented, so results may be committed; they are written to results/.
"""

import argparse
import asyncio
import json
import shlex
from dataclasses import asdict
from datetime import date, datetime
from typing import Any

import anthropic

from app.agent.loop import Limits, Model, answer_question
from app.agent.mcp_tools import mcp_toolbox
from app.config import Settings
from eval import assistant_data, fake_api
from eval.assistant_questions import QUESTIONS, Question, grade
from eval.run import PRICES, ROOT, cost

# Measured: about 4,000 tokens in and 400 out a question, over two model calls.
TOKENS_IN, TOKENS_OUT = 5_000, 600


async def ask_all(
    questions: list[Question], api_url: str, model: Model, model_name: str, settings: Settings
) -> list[dict[str, Any]]:
    today = date.fromisoformat(assistant_data.TODAY)
    rows = []
    for q in questions:
        async with mcp_toolbox(
            settings.mcp_server_command, shlex.split(settings.mcp_server_args), api_url, None
        ) as toolbox:
            result = await answer_question(
                q.text, [], toolbox, model, model_name, Limits(), today=today
            )
        g = grade(q, result.answer)
        rows.append(
            {
                "id": q.id,
                "passed": g.passed,
                "missing": g.missing,
                "outcome": result.outcome,
                "tools": result.tool_calls,
                "model_calls": result.model_calls,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "seconds": round(result.seconds, 1),
                "answer": result.answer,
            }
        )
        mark = "pass" if g.passed else "FAIL"
        print(f"  {mark}  {q.id:<28} {','.join(result.tool_calls) or '-'}")
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--claude", metavar="MODEL", required=True, help="Claude model (paid)")
    parser.add_argument("--runs", type=int, default=1, help="repeat the whole set")
    parser.add_argument("--only", nargs="*", help="question ids")
    parser.add_argument("--yes", action="store_true", help="skip the cost confirmation")
    args = parser.parse_args()

    questions = [q for q in QUESTIONS if not args.only or q.id in args.only]
    n = len(questions) * args.runs
    print(
        f"{len(questions)} questions x {args.runs} run(s) on {args.claude}: about "
        f"${cost(args.claude, TOKENS_IN * n, TOKENS_OUT * n):.3f} (upper estimate)"
    )
    if not args.yes and input("Run it? [y/N] ").strip().lower() != "y":
        return

    settings = Settings()
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key, max_retries=2)
    model: Model = client.messages  # type: ignore[assignment]
    runs = []
    with fake_api.serve() as api_url:
        for run in range(args.runs):
            print(f"Run {run + 1}:")
            runs.append(asyncio.run(ask_all(questions, api_url, model, args.claude, settings)))

    print()
    for i, rows in enumerate(runs, 1):
        tokens_in = sum(r["input_tokens"] for r in rows)
        tokens_out = sum(r["output_tokens"] for r in rows)
        passed = sum(r["passed"] for r in rows)
        print(
            f"Run {i}: {passed}/{len(rows)} passed, "
            f"{sum(r['model_calls'] for r in rows)} model calls, "
            f"{tokens_in} tokens in / {tokens_out} out, "
            f"{sum(r['seconds'] for r in rows):.0f}s"
            + (
                f", ${cost(args.claude, tokens_in, tokens_out):.4f}"
                if args.claude in PRICES
                else ""
            )
        )
        for r in rows:
            if not r["passed"]:
                print(f"    {r['id']}: missing {r['missing']}\n      {r['answer'][:300]!r}")

    out = ROOT / "results"
    out.mkdir(exist_ok=True)
    path = out / f"assistant-{datetime.now():%Y%m%d-%H%M%S}.json"
    path.write_text(
        json.dumps(
            {
                "model": args.claude,
                "questions": [asdict(q) for q in questions],
                "runs": runs,
            },
            indent=2,
        )
    )
    print(f"\nSaved {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
