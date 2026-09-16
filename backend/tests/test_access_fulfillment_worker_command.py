from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from backend.commands import process_access_fulfillments as command
from services.subscriber_fulfillment_service import process_due_fulfillments


class _Result:
    def __init__(
        self,
        *,
        processed=0,
        delivered=0,
        retryable_failures=0,
        terminal_failures=0,
        cancelled=0,
    ):
        self.processed = processed
        self.delivered = delivered
        self.retryable_failures = retryable_failures
        self.terminal_failures = terminal_failures
        self.cancelled = cancelled


def _fake_service(calls: list[dict], result: _Result | None = None):
    async def process_due_fulfillments(*, limit, now):
        calls.append({"limit": limit, "now": now})
        return result or _Result()

    return SimpleNamespace(
        FULFILLMENT_PROCESS_MAX_LIMIT=2,
        process_due_fulfillments=process_due_fulfillments,
    )


def test_worker_default_limit_calls_service_directly(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(command, "_load_fulfillment_service", lambda: _fake_service(calls))

    assert command.main([]) == 0

    assert calls and calls[0]["limit"] == 1
    assert json.loads(capsys.readouterr().out) == {
        "cancelled": 0,
        "delivered": 0,
        "processed": 0,
        "retryable_failures": 0,
        "terminal_failures": 0,
    }


def test_worker_valid_explicit_limit_outputs_safe_counts(monkeypatch, capsys):
    calls = []
    result = _Result(
        processed=2,
        delivered=1,
        retryable_failures=1,
        terminal_failures=0,
        cancelled=0,
    )
    monkeypatch.setattr(
        command,
        "_load_fulfillment_service",
        lambda: _fake_service(calls, result=result),
    )

    assert command.main(["--limit", "2"]) == 0

    output = capsys.readouterr().out
    assert json.loads(output) == {
        "cancelled": 0,
        "delivered": 1,
        "processed": 2,
        "retryable_failures": 1,
        "terminal_failures": 0,
    }
    assert "secret" not in output.lower()
    assert "invite" not in output.lower()
    assert "subscriber" not in output.lower()
    assert "chat_id" not in output.lower()
    assert calls[0]["limit"] == 2


@pytest.mark.parametrize("limit", ["0", "3"])
def test_worker_rejects_invalid_limits(monkeypatch, capsys, limit):
    calls = []
    monkeypatch.setattr(command, "_load_fulfillment_service", lambda: _fake_service(calls))

    assert command.main(["--limit", limit]) == 2

    captured = capsys.readouterr()
    assert "between 1 and 2" in captured.err
    assert calls == []


def test_worker_fatal_failure_returns_nonzero_without_leaking_details(monkeypatch, capsys):
    async def fail(*, limit, now):
        raise RuntimeError("raw invite url subscriber@example.com database-url")

    service = SimpleNamespace(
        FULFILLMENT_PROCESS_MAX_LIMIT=2,
        process_due_fulfillments=fail,
    )
    monkeypatch.setattr(command, "_load_fulfillment_service", lambda: service)

    assert command.main(["--limit", "1"]) == 1

    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "access fulfillment worker execution failed" in combined
    assert "raw invite" not in combined
    assert "subscriber@example.com" not in combined
    assert "database-url" not in combined


def test_worker_initialization_failure_returns_nonzero_without_leaking_details(
    monkeypatch,
    capsys,
):
    def fail_load():
        raise RuntimeError("DATABASE_URL=sqlite:///secret.db")

    monkeypatch.setattr(command, "_load_fulfillment_service", fail_load)

    assert command.main([]) == 1

    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "worker initialization failed" in combined
    assert "secret.db" not in combined


def test_fulfillment_service_closes_sessions_when_no_due_work():
    class FakeSession:
        def __init__(self):
            self.closed = False

        def query(self, *args, **kwargs):
            return self

        def filter(self, *args, **kwargs):
            return self

        def order_by(self, *args, **kwargs):
            return self

        def first(self):
            return None

        def close(self):
            self.closed = True

    sessions: list[FakeSession] = []

    def session_factory():
        session = FakeSession()
        sessions.append(session)
        return session

    result = asyncio.run(
        process_due_fulfillments(
            limit=1,
            session_factory=session_factory,
            now=command.datetime.now(command.timezone.utc),
        )
    )

    assert result.processed == 0
    assert sessions
    assert all(session.closed for session in sessions)
