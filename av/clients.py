"""Injectable model clients. Every hosted call in the project goes through `hosted()` so that
av.quota counts it (CLAUDE.md rule 7).

- hosted(): OpenCode Go, assumed OpenAI-compatible (OPENCODE_GO_BASE_URL, OPENCODE_GO_API_KEY
  from .env). Checks the budget before, and counts the call after, every request.
- ollama(): the local Ollama server (OLLAMA_BASE_URL, default http://localhost:11434). Callers
  making more than a handful of calls hold av.gpu.gpu_lock().
- use_clients(): swaps in other clients (tests inject fakes; see tests/conftest.py, which also
  makes the real clients raise).
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Protocol

from av import quota
from av.config import load_env

Message = dict[str, Any]


@dataclass(frozen=True)
class ChatResult:
    text: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    raw: Any = field(default=None, repr=False)


class ChatClient(Protocol):
    def chat(self, messages: list[Message], model: str | None = None, **kwargs: Any) -> ChatResult: ...


class RealClientBlocked(RuntimeError):
    """A test (or offline replay) reached a real model client."""


#: Set True by tests/conftest.py: constructing a real client then raises.
BLOCK_REAL_CLIENTS = False


def _refuse_if_blocked(kind: str) -> None:
    if BLOCK_REAL_CLIENTS:
        raise RealClientBlocked(f"real {kind} client used while real clients are blocked (tests are offline)")


class HostedClient:
    """OpenAI-compatible chat client for OpenCode Go. Quota-checked and counted per call."""

    def __init__(self, base_url: str, api_key: str, default_model: str | None = None, timeout: float = 120):
        _refuse_if_blocked("hosted")
        from openai import OpenAI

        self.default_model = default_model
        self._client = OpenAI(base_url=base_url, api_key=api_key, timeout=timeout, max_retries=0)

    def chat(self, messages: list[Message], model: str | None = None, **kwargs: Any) -> ChatResult:
        _refuse_if_blocked("hosted")
        model = model or self.default_model
        if not model:
            raise ValueError("no model given and no default_model set")
        quota.assert_budget(1)
        pt = ct = 0
        try:
            resp = self._client.chat.completions.create(model=model, messages=messages, **kwargs)
            if resp.usage is not None:
                pt, ct = resp.usage.prompt_tokens or 0, resp.usage.completion_tokens or 0
            text = resp.choices[0].message.content or ""
            return ChatResult(text=text, model=model, prompt_tokens=pt, completion_tokens=ct, raw=resp)
        finally:
            # Count attempts too: a failed request may still have used quota upstream.
            quota.record(1, prompt_tokens=pt, completion_tokens=ct)


class OllamaClient:
    """Minimal client for Ollama's /api/chat (non-streaming). Not counted by quota."""

    def __init__(self, base_url: str = "http://localhost:11434", default_model: str | None = None, timeout: float = 300):
        _refuse_if_blocked("ollama")
        import httpx

        self.default_model = default_model
        self._http = httpx.Client(base_url=base_url, timeout=timeout)

    def chat(self, messages: list[Message], model: str | None = None, **kwargs: Any) -> ChatResult:
        _refuse_if_blocked("ollama")
        model = model or self.default_model
        if not model:
            raise ValueError("no model given and no default_model set")
        r = self._http.post("/api/chat", json={"model": model, "messages": messages, "stream": False, **kwargs})
        r.raise_for_status()
        data = r.json()
        return ChatResult(
            text=data.get("message", {}).get("content", ""),
            model=model,
            prompt_tokens=data.get("prompt_eval_count", 0),
            completion_tokens=data.get("eval_count", 0),
            raw=data,
        )


def _real_hosted() -> ChatClient:
    load_env()
    base_url = os.environ.get("OPENCODE_GO_BASE_URL")
    api_key = os.environ.get("OPENCODE_GO_API_KEY")
    if not base_url or not api_key:
        raise RuntimeError("OPENCODE_GO_BASE_URL and OPENCODE_GO_API_KEY must be set in .env")
    return HostedClient(base_url=base_url, api_key=api_key, default_model=os.environ.get("AV_HOSTED_MODEL"))


def _real_ollama() -> ChatClient:
    load_env()
    return OllamaClient(
        base_url=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"),
        default_model=os.environ.get("AV_OLLAMA_MODEL"),
    )


_hosted_override: ChatClient | None = None
_ollama_override: ChatClient | None = None


def hosted() -> ChatClient:
    """The hosted (OpenCode Go) client, or the injected one."""
    return _hosted_override if _hosted_override is not None else _real_hosted()


def ollama() -> ChatClient:
    """The local Ollama client, or the injected one."""
    return _ollama_override if _ollama_override is not None else _real_ollama()


@contextmanager
def use_clients(hosted: ChatClient | None = None, ollama: ChatClient | None = None) -> Iterator[None]:
    """Temporarily inject clients (None leaves that one unchanged). For tests and fakes only:
    an injected client is NOT counted by av.quota, so never inject a real hosted client."""
    global _hosted_override, _ollama_override
    prev = (_hosted_override, _ollama_override)
    if hosted is not None:
        _hosted_override = hosted
    if ollama is not None:
        _ollama_override = ollama
    try:
        yield
    finally:
        _hosted_override, _ollama_override = prev
