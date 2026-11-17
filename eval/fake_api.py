"""A stand-in for the Expense Tracker API, serving the invented eval data
(eval/assistant_data.py) in the shapes BE/ returns, for the endpoints the MCP
server calls. Local HTTP on a free port, in a background thread."""

import json
import socketserver
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from eval import assistant_data as data


def _expense_json(i: int, e: data.Expense) -> dict[str, Any]:
    return {
        "id": f"e{i}",
        "datePosted": e.date,
        "description": e.description,
        "amount": f"{e.amount:.2f}",
        "currency": e.currency,
        "category": e.category,
        "account": e.account,
        "isGift": False,
    }


def categories() -> list[dict[str, Any]]:
    groups = sorted({group for _, group, _ in data.CATEGORIES})
    rows: list[dict[str, Any]] = [
        {"id": f"g{i}", "name": g, "parentCategoryId": None, "budget": None}
        for i, g in enumerate(groups)
    ]
    for i, (name, group, budget) in enumerate(data.CATEGORIES):
        rows.append(
            {
                "id": f"c{i}",
                "name": name,
                "parentCategoryId": f"g{groups.index(group)}",
                "budget": budget,
            }
        )
    return rows


def monthly_totals() -> list[dict[str, Any]]:
    months = sorted({data.month_of(e) for e in data.EXPENSES})
    rows = [
        {
            "id": f"expense-{m}",
            "type": "expense",
            "yearMonth": m,
            "amountCad": f"{data.spent(m, 'CAD'):.2f}",
            "amountUsd": f"{data.spent(m, 'USD'):.2f}",
        }
        for m in months
    ]
    income_usd = sum(r[2] for r in data.RECURRING_INCOME if r[3] == "USD")
    rows += [
        {
            "id": f"income-{m}",
            "type": "income",
            "yearMonth": m,
            "amountCad": "0.00",
            "amountUsd": f"{income_usd:.2f}",
        }
        for m in months
    ]
    return rows


def monthly_report(month: str) -> dict[str, Any]:
    # As BE/ does: per-category "total" adds currencies; the tool doesn't use it.
    groups: dict[str, dict[str, Any]] = {}
    for e in data.EXPENSES:
        if data.month_of(e) != month:
            continue
        entry = groups.setdefault(e.category, {"category": e.category, "total": 0.0, "details": []})
        entry["total"] = data.r2(entry["total"] + e.amount)
        entry["details"].append(
            {"description": e.description, "amount": e.amount, "currency": e.currency}
        )
    for entry in groups.values():
        entry["details"].sort(key=lambda d: -d["amount"])
    return {
        "yearMonth": month,
        "dataByCategory": sorted(groups.values(), key=lambda g: -g["total"]),
        "totalSpentCad": data.spent(month, "CAD"),
        "totalSpentUsd": data.spent(month, "USD"),
    }


def expenses(month: str | None, search: str | None) -> dict[str, Any]:
    rows = [(i, e) for i, e in enumerate(data.EXPENSES)]
    if month:
        rows = [(i, e) for i, e in rows if data.month_of(e) == month]
    elif search:
        needle = search.lower()
        rows = [
            (i, e)
            for i, e in rows
            if needle in e.description.lower() or needle in e.category.lower()
        ]
    rows.sort(key=lambda pair: pair[1].date, reverse=True)
    return {"data": [_expense_json(i, e) for i, e in rows], "expensesTotal": {}}


def route(path: str, query: dict[str, list[str]]) -> tuple[int, Any]:
    first = {k: v[0] for k, v in query.items()}
    if path == "/categories":
        return 200, categories()
    if path == "/monthlyData":
        return 200, monthly_totals()
    if path == "/reports/monthly":
        return 200, monthly_report(first.get("yearMonth", ""))
    if path == "/expenses":
        return 200, expenses(first.get("yearMonth"), first.get("search"))
    if path == "/recurringExpenses":
        return 200, [
            {
                "description": d,
                "category": c,
                "amount": f"{a:.2f}",
                "currency": cur,
                "account": "Card",
                "dayOfMonth": day,
            }
            for d, c, a, cur, day in data.RECURRING_EXPENSES
        ]
    if path == "/recurringIncome":
        return 200, [
            {"description": d, "category": c, "amount": f"{a:.2f}", "currency": cur}
            for d, c, a, cur in data.RECURRING_INCOME
        ]
    return 404, {"error": "not found"}


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        url = urlparse(self.path)
        status, body = route(url.path, parse_qs(url.query))
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self) -> None:  # The assistant never writes; refuse loudly if it tries.
        self.send_response(405)
        self.end_headers()

    def log_message(self, format: str, *args: Any) -> None:
        pass


class _Server(ThreadingHTTPServer):
    def server_bind(self) -> None:
        # HTTPServer looks its own name up in DNS here, which can hang for
        # half a minute; a local test server doesn't need a name.
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = "127.0.0.1", self.server_address[1]


@contextmanager
def serve() -> Iterator[str]:
    server = _Server(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
