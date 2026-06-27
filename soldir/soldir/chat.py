from __future__ import annotations

import json
import os
from typing import Any

import httpx

from soldir.models import ChatRequest


DEFAULT_MODELS = {
    "grok": "latest",
    "openai": "gpt-4.1-mini",
    "claude": "claude-sonnet-4-20250514",
    "ollama": "llama3.2",
}


class ChatProviderError(RuntimeError):
    pass


def _graph_digest(snapshot: dict[str, Any]) -> str:
    nodes = snapshot.get("nodes", [])
    links = snapshot.get("links", [])
    compact = {
        "node_count": len(nodes),
        "edge_count": len(links),
        "nodes": [
            {
                "id": node.get("id"),
                "hostname": node.get("hostname"),
                "os": node.get("os"),
                "arch": node.get("arch"),
                "last_seen": node.get("last_seen"),
                "status": node.get("status"),
            }
            for node in nodes[:40]
        ],
        "links": [
            {
                "source": link.get("source"),
                "target": link.get("target"),
                "type": link.get("type"),
                "label": link.get("label"),
                "last_seen": link.get("last_seen"),
                "count": link.get("count"),
            }
            for link in links[:80]
        ],
    }
    return json.dumps(compact, indent=2, sort_keys=True)


def _system_prompt(snapshot: dict[str, Any]) -> str:
    return (
        "You are Soldir, an operations copilot for a realtime Tailor instance "
        "network graph. Answer tersely, ground conclusions in the graph snapshot, "
        "and call out uncertainty when the graph is incomplete.\n\n"
        f"Current graph snapshot:\n{_graph_digest(snapshot)}"
    )


async def complete_chat(request: ChatRequest, snapshot: dict[str, Any]) -> str:
    provider = request.provider.strip().lower()
    if provider in {"grok", "xai"}:
        return await _openai_compatible(
            api_key_env="XAI_API_KEY",
            base_url=os.getenv("XAI_BASE_URL", "https://api.x.ai/v1"),
            model=request.model or os.getenv("XAI_MODEL") or DEFAULT_MODELS["grok"],
            request=request,
            snapshot=snapshot,
        )
    if provider == "openai":
        return await _openai_compatible(
            api_key_env="OPENAI_API_KEY",
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            model=request.model or os.getenv("OPENAI_MODEL") or DEFAULT_MODELS["openai"],
            request=request,
            snapshot=snapshot,
        )
    if provider in {"claude", "anthropic"}:
        return await _claude(request, snapshot)
    if provider == "ollama":
        return await _ollama(request, snapshot)
    raise ChatProviderError(f"Unsupported provider: {request.provider}")


async def _openai_compatible(
    *,
    api_key_env: str,
    base_url: str,
    model: str,
    request: ChatRequest,
    snapshot: dict[str, Any],
) -> str:
    api_key = os.getenv(api_key_env)
    if not api_key:
        raise ChatProviderError(f"Set {api_key_env} before using this provider.")

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _system_prompt(snapshot)},
            {"role": "user", "content": request.message},
        ],
        "temperature": 0.2,
    }
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            f"{base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
        )
    if response.status_code >= 400:
        raise ChatProviderError(f"Provider returned {response.status_code}: {response.text}")
    data = response.json()
    return data["choices"][0]["message"]["content"]


async def _claude(request: ChatRequest, snapshot: dict[str, Any]) -> str:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ChatProviderError("Set ANTHROPIC_API_KEY before using Claude.")
    base_url = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com/v1")
    model = request.model or os.getenv("ANTHROPIC_MODEL") or DEFAULT_MODELS["claude"]
    payload = {
        "model": model,
        "max_tokens": 1200,
        "system": _system_prompt(snapshot),
        "messages": [{"role": "user", "content": request.message}],
    }
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            f"{base_url.rstrip('/')}/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json=payload,
        )
    if response.status_code >= 400:
        raise ChatProviderError(f"Claude returned {response.status_code}: {response.text}")
    data = response.json()
    return "".join(part.get("text", "") for part in data.get("content", []))


async def _ollama(request: ChatRequest, snapshot: dict[str, Any]) -> str:
    base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    model = request.model or os.getenv("OLLAMA_MODEL") or DEFAULT_MODELS["ollama"]
    payload = {
        "model": model,
        "stream": False,
        "messages": [
            {"role": "system", "content": _system_prompt(snapshot)},
            {"role": "user", "content": request.message},
        ],
        "options": {"temperature": 0.2},
    }
    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(f"{base_url.rstrip('/')}/api/chat", json=payload)
    if response.status_code >= 400:
        raise ChatProviderError(f"Ollama returned {response.status_code}: {response.text}")
    data = response.json()
    return data.get("message", {}).get("content", "")
