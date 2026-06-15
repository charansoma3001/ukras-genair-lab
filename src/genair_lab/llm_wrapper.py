"""Builds the LLM client.

We route through Ollama's native /api/chat with streaming for two reasons:
  1. To turn thinking on/off (the /v1 endpoint ignores ``think``).
  2. To fire an ``on_thinking_done`` callback when the reasoning pass ends, so the
     UI can switch from "thinking" to "deciding".

If the native call fails (e.g. on a non-Ollama server like llama-server) we fall
back to the OpenAI /v1 endpoint. Thinking control and the callback aren't
available then, but everything else works the same.
"""

import json
import os
import urllib.request
from typing import Callable, Dict, List, Optional

from dotenv import load_dotenv

load_dotenv()


DEFAULT_BASE_URL = "http://localhost:11434/v1"
DEFAULT_MODEL = "qwen2.5:1.5b"


def _env(*names: str, default: str = "") -> str:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return default


# --- Tiny OpenAI-shape wrappers so the loop never has to know which path ran --
class _Fn:
    def __init__(self, name, arguments): self.name = name; self.arguments = arguments
class _ToolCall:
    def __init__(self, id, name, arguments):
        self.id = id; self.type = "function"; self.function = _Fn(name, arguments)
class _Msg:
    def __init__(self, content, tool_calls): self.content = content; self.tool_calls = tool_calls
class _Resp:
    def __init__(self, message, prompt_tokens=None):
        self.choices = [type("C", (), {"message": message})()]
        self.prompt_tokens = prompt_tokens


def _probe_native(native_url: str) -> bool:
    """Return True if this looks like an Ollama server (has /api/tags)."""
    tags_url = native_url.replace("/api/chat", "/api/tags")
    try:
        urllib.request.urlopen(tags_url, timeout=3)
        return True
    except Exception:
        return False


def _native_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3]
    return base.rstrip("/") + "/api/chat"


def _to_native_messages(messages: List[Dict]) -> List[Dict]:
    """Convert OpenAI-format message history to Ollama native format.

    OpenAI assistant tool_calls: list of {id, type, function: {name, arguments: str}}
    Ollama native expects:       list of {function: {name, arguments: dict}}  (no id/type)

    OpenAI tool result: {role:"tool", tool_call_id:..., name:..., content:...}
    Ollama native:      {role:"tool", content:...}  (no tool_call_id / name)
    """
    out = []
    for m in messages:
        role = m.get("role")
        if role == "assistant" and m.get("tool_calls"):
            tcs = []
            for tc in m["tool_calls"]:
                fn = tc.get("function", {})
                args = fn.get("arguments", {})
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except Exception:
                        args = {}
                tcs.append({"function": {"name": fn.get("name"), "arguments": args}})
            out.append({"role": "assistant", "content": m.get("content") or "", "tool_calls": tcs})
        elif role == "tool":
            out.append({"role": "tool", "content": m.get("content", "")})
        else:
            out.append(m)
    return out


def _native_stream(url: str, model: str, messages: List[Dict],
                   tools: Optional[List[Dict]], think: bool,
                   on_thinking_done: Optional[Callable] = None) -> _Resp:
    """Stream Ollama's native /api/chat, fire callback when thinking ends."""
    body = {"model": model, "messages": _to_native_messages(messages), "stream": True, "think": think}
    if tools:
        body["tools"] = tools
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})

    content, tool_calls, prompt_tokens = "", [], None
    thinking_done_fired = not think  # if think=False, no reasoning pass to wait for

    with urllib.request.urlopen(req, timeout=300) as r:
        for raw in r:
            raw = raw.strip()
            if not raw:
                continue
            chunk = json.loads(raw)
            m = chunk.get("message", {})

            # Fire callback the first time we see content/tool tokens after thinking.
            if not thinking_done_fired and (m.get("content") or m.get("tool_calls")):
                thinking_done_fired = True
                if on_thinking_done:
                    on_thinking_done()

            content += m.get("content") or ""
            if m.get("tool_calls"):
                tool_calls = m["tool_calls"]

            if chunk.get("done"):
                # Tokens the model read this turn (prompt + history + observation).
                prompt_tokens = chunk.get("prompt_eval_count")
                break

    calls = []
    for i, tc in enumerate(tool_calls):
        fn = tc.get("function", {})
        args = fn.get("arguments")
        if not isinstance(args, str):
            args = json.dumps(args or {})
        calls.append(_ToolCall(tc.get("id") or f"call_{i}", fn.get("name"), args))
    return _Resp(_Msg(content, calls or None), prompt_tokens=prompt_tokens)


def create_openai_client(api_key: str = None, model: str = None, base_url: str = None,
                         think: bool = False, **_ignored):
    """Create an LLM callable for the GenAIR loop.

    Args:
        model:    Model name. Defaults to ``MODEL_NAME``.
        base_url: Endpoint URL. Defaults to ``MODEL_BASE_URL``.
        api_key:  API key (any non-empty string works for Ollama / llama-server).
        think:    Pass ``True`` to enable the model's reasoning pass. Default
                  ``False`` (faster, no reasoning). Only effective on Ollama.

    Returns:
        ``call_llm(messages, tools, on_thinking_done=None) -> response``
        where ``on_thinking_done`` is an optional zero-arg callback fired the
        moment the reasoning pass finishes (thinking=True only).
    """
    if api_key is None:
        api_key = _env("MODEL_API_KEY", "ollama_api_key", default="ollama")
    if model is None:
        model = _env("MODEL_NAME", "ollama_model", default=DEFAULT_MODEL)
    if base_url is None:
        base_url = _env("MODEL_BASE_URL", "ollama_url", default=DEFAULT_BASE_URL)

    import openai
    client = openai.OpenAI(base_url=base_url, api_key=api_key)
    native_url = _native_url(base_url)

    # Probe once: if the native /api/chat endpoint isn't reachable (e.g. llama-server),
    # skip it on every subsequent call instead of eating a failed attempt each time.
    is_ollama = _probe_native(native_url)

    def call_llm(messages: List[Dict], tools: List[Dict] = None,
                 on_thinking_done: Callable = None, **kwargs) -> _Resp:
        if is_ollama:
            resp = _native_stream(native_url, model, messages, tools, think, on_thinking_done)
            call_llm.last_prompt_tokens = resp.prompt_tokens
            return resp
        # Non-Ollama server: straight to /v1.
        call_kwargs = {"model": model, "messages": messages}
        if tools:
            call_kwargs["tools"] = tools
            call_kwargs["tool_choice"] = "auto"
        call_kwargs.update(kwargs)
        resp = client.chat.completions.create(**call_kwargs)
        usage = getattr(resp, "usage", None)
        call_llm.last_prompt_tokens = getattr(usage, "prompt_tokens", None)
        return resp

    call_llm.model_name = model
    call_llm.base_url = base_url
    call_llm.think = think
    call_llm.last_prompt_tokens = None  # tokens read by the model on the last turn
    return call_llm
