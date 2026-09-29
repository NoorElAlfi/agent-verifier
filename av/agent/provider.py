"""Inspect model provider `av-hosted/<model>`: every generate() goes through `av.clients.hosted()`.

That is what makes Inspect's model calls count against the quota (CLAUDE.md rule 7):
`HostedClient.chat` asserts the budget before, and records tokens after, every call. Offline
tests inject a fake hosted client (`av.clients.use_clients`), so no network is reached.

Inspect's own OpenAI-compatible provider (`openai-api/<service>/<model>`) would call the API
directly and bypass av.quota, so it is deliberately not used.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from inspect_ai.model import (
    ChatMessage,
    GenerateConfig,
    ModelAPI,
    ModelOutput,
    modelapi,
)
from inspect_ai.model._openai import (
    chat_choices_from_openai,
    messages_to_openai,
    model_output_from_openai,
    openai_chat_tool_choice,
    openai_chat_tools,
)
from inspect_ai.tool import ToolChoice, ToolInfo
from openai.types.chat import ChatCompletion

from av import clients


def _completion_from_text(text: str, model: str) -> ChatCompletion:
    """Wrap a text-only reply (e.g. from a plain fake client) as a ChatCompletion."""
    return ChatCompletion.model_validate(
        {
            "id": "av-fake",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": text}}],
        }
    )


class EmptyModelReply(RuntimeError):
    """The hosted model returned nothing usable; the episode is recorded as an error."""


@modelapi(name="av-hosted")
class AvHostedAPI(ModelAPI):
    def __init__(
        self,
        model_name: str,
        base_url: str | None = None,
        api_key: str | None = None,
        config: GenerateConfig = GenerateConfig(),
        **model_args: Any,
    ) -> None:
        # No keys here: av.clients.hosted() reads them from .env when it is first used.
        super().__init__(model_name=model_name, base_url=None, api_key=None, api_key_vars=[], config=config)

    def max_connections(self) -> int:
        return 1  # one call at a time keeps quota accounting simple

    async def generate(
        self,
        input: list[ChatMessage],
        tools: list[ToolInfo],
        tool_choice: ToolChoice,
        config: GenerateConfig,
    ) -> ModelOutput:
        messages = await messages_to_openai(input)
        kwargs: dict[str, Any] = {}
        if tools:
            kwargs["tools"] = openai_chat_tools(tools)
            kwargs["tool_choice"] = openai_chat_tool_choice(tool_choice)
        if config.max_tokens is not None:
            kwargs["max_tokens"] = config.max_tokens
        if config.temperature is not None:
            kwargs["temperature"] = config.temperature
        client = clients.hosted()
        result = await asyncio.to_thread(client.chat, messages, self.model_name, **kwargs)  # type: ignore[arg-type]
        raw = result.raw if isinstance(result.raw, ChatCompletion) else _completion_from_text(result.text, self.model_name)
        output = model_output_from_openai(raw, chat_choices_from_openai(raw, tools))
        msg = output.message
        if not (msg.text or "").strip() and not msg.tool_calls:
            # Fail loud: an empty reply with no tool calls must not look like a finished episode.
            raise EmptyModelReply(f"model {self.model_name} returned an empty reply with no tool calls")
        return output
