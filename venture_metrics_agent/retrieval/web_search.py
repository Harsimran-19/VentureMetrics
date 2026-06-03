"""Tavily web fallback adapter."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


TAVILY_SEARCH_URL = "https://api.tavily.com/search"


@dataclass(frozen=True)
class WebResult:
    title: str
    url: str
    content: str
    score: float | None = None

    def citation(self) -> dict[str, Any]:
        return {
            "title": self.title or self.url,
            "url": self.url,
            "source_type": "web",
            "reliability": "needs_review",
        }


def tavily_search(query: str, *, max_results: int = 5, api_key: str | None = None, timeout: float = 30.0) -> list[WebResult]:
    key = api_key or os.environ.get("TAVILY_API_KEY") or _read_env_value("TAVILY_API_KEY")
    if not key:
        raise RuntimeError("TAVILY_API_KEY is missing. Add it to .env or export it in the shell.")

    payload = json.dumps(
        {
            "query": query,
            "search_depth": "advanced",
            "max_results": max_results,
            "include_answer": False,
            "include_raw_content": False,
        }
    ).encode("utf-8")
    request = Request(
        TAVILY_SEARCH_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Tavily Search HTTP {exc.code}: {error_body}") from exc
    except URLError as exc:
        raise RuntimeError(f"Tavily Search connection failed: {exc.reason}") from exc

    results = []
    for item in body.get("results", []):
        url = str(item.get("url") or "").strip()
        if not url:
            continue
        results.append(
            WebResult(
                title=str(item.get("title") or url).strip(),
                url=url,
                content=str(item.get("content") or "").strip(),
                score=item.get("score"),
            )
        )
    return results


def web_results_to_context(results: list[WebResult], *, max_chars: int = 5000, start_index: int = 1) -> str:
    blocks: list[str] = []
    remaining = max_chars
    for index, result in enumerate(results, start=start_index):
        content = result.content[:900].strip()
        block = f"[{index}] {result.title}\nURL: {result.url}\nEvidence: {content}"
        if len(block) > remaining:
            break
        blocks.append(block)
        remaining -= len(block)
    return "\n\n".join(blocks)


def _read_env_value(key: str, env_path: str | Path = ".env") -> str | None:
    path = Path(env_path)
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, value = stripped.split("=", 1)
        if name.strip() == key:
            return value.strip().strip('"').strip("'")
    return None
