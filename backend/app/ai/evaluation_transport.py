"""Optional evaluation-only send boundary; ordinary provider calls remain unchanged."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Protocol


class EvaluationTransport(Protocol):
    def open(self, request, *, timeout: int): ...


_transport: ContextVar[EvaluationTransport | None] = ContextVar("m9b_evaluation_transport", default=None)


@contextmanager
def evaluation_transport(transport: EvaluationTransport):
    token = _transport.set(transport)
    try:
        yield
    finally:
        _transport.reset(token)


def active_evaluation_transport() -> EvaluationTransport | None:
    return _transport.get()
