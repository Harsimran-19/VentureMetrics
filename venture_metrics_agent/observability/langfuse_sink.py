"""Optional Langfuse exporter for local telemetry records."""

from __future__ import annotations

import importlib
import importlib.util
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


TRUE_VALUES = {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class LangfuseConfig:
    enabled: bool = False
    public_key: str | None = None
    secret_key: str | None = None
    base_url: str | None = None
    environment: str | None = None
    release: str | None = None
    sample_rate: float | None = None

    @property
    def is_configured(self) -> bool:
        return self.enabled and bool(self.public_key and self.secret_key)


def load_langfuse_config(env_path: str | Path = ".env") -> LangfuseConfig:
    env_values = _read_env_file(env_path)
    enabled = _env("LANGFUSE_ENABLED", env_values, default="false").lower() in TRUE_VALUES
    sample_rate = _float_or_none(_env("LANGFUSE_SAMPLE_RATE", env_values, default=""))
    return LangfuseConfig(
        enabled=enabled,
        public_key=_env("LANGFUSE_PUBLIC_KEY", env_values),
        secret_key=_env("LANGFUSE_SECRET_KEY", env_values),
        base_url=_env("LANGFUSE_BASE_URL", env_values) or _env("LANGFUSE_HOST", env_values),
        environment=_env("LANGFUSE_ENVIRONMENT", env_values) or _env("LANGFUSE_TRACING_ENVIRONMENT", env_values),
        release=_env("LANGFUSE_RELEASE", env_values),
        sample_rate=sample_rate,
    )


def export_agent_response_to_langfuse(
    question: str,
    response: dict[str, Any],
    *,
    agent_name: str,
    session_external_id: str | None,
    local_run_id: int | None,
    metadata: dict[str, Any] | None = None,
    config: LangfuseConfig | None = None,
) -> None:
    config = config or load_langfuse_config()
    if not config.is_configured:
        return

    try:
        langfuse_module = importlib.import_module("langfuse")
    except ImportError:
        return

    try:
        client = _create_client(langfuse_module, config)
        _export_trace(
            client,
            question,
            response,
            agent_name=agent_name,
            session_external_id=session_external_id,
            local_run_id=local_run_id,
            metadata=metadata or {},
        )
        flush = getattr(client, "flush", None)
        if callable(flush):
            flush()
    except Exception:
        # Langfuse is a dashboard sink, not the product source of truth.
        return


def langfuse_status(config: LangfuseConfig | None = None) -> dict[str, Any]:
    config = config or load_langfuse_config()
    return {
        "enabled": config.enabled,
        "configured": config.is_configured,
        "sdk_installed": importlib.util.find_spec("langfuse") is not None,
        "base_url": config.base_url or "https://cloud.langfuse.com",
        "environment": config.environment,
        "release": config.release,
        "sample_rate": config.sample_rate,
    }


def _create_client(langfuse_module: Any, config: LangfuseConfig) -> Any:
    client_cls = getattr(langfuse_module, "Langfuse", None)
    if client_cls is not None:
        kwargs: dict[str, Any] = {
            "public_key": config.public_key,
            "secret_key": config.secret_key,
        }
        if config.base_url:
            kwargs["base_url"] = config.base_url
        if config.environment:
            kwargs["environment"] = config.environment
        if config.release:
            kwargs["release"] = config.release
        if config.sample_rate is not None:
            kwargs["sample_rate"] = config.sample_rate
        return client_cls(**kwargs)

    get_client = getattr(langfuse_module, "get_client")
    return get_client()


def _export_trace(
    client: Any,
    question: str,
    response: dict[str, Any],
    *,
    agent_name: str,
    session_external_id: str | None,
    local_run_id: int | None,
    metadata: dict[str, Any],
) -> None:
    root_name = f"venture_metrics.{agent_name}"
    trace_metadata = {
        **metadata,
        "local_run_id": local_run_id,
        "confidence": response.get("confidence"),
        "source_mode": response.get("source_mode"),
        "used_web_fallback": bool(response.get("used_web_fallback")),
        "citation_count": len(response.get("citations") or []),
        "gap_count": len(response.get("gaps") or []),
    }

    with client.start_as_current_observation(as_type="agent", name=root_name) as root:
        _update_current_trace(
            client,
            name=root_name,
            question=question,
            response=response,
            session_external_id=session_external_id,
            metadata=trace_metadata,
        )
        root.update(
            input=question,
            output=response.get("answer", ""),
            metadata=trace_metadata,
        )
        _export_steps(root, response.get("reasoning_trace") or [])
        _export_retrieval(root, "internal_retrieval", response.get("retrieved_evidence") or [])
        _export_retrieval(root, "web_retrieval", response.get("web_evidence") or [])
        _export_citations(root, response.get("citations") or [])


def _update_current_trace(
    client: Any,
    *,
    name: str,
    question: str,
    response: dict[str, Any],
    session_external_id: str | None,
    metadata: dict[str, Any],
) -> None:
    update_current_trace = getattr(client, "update_current_trace", None)
    if not callable(update_current_trace):
        return
    kwargs = {
        "name": name,
        "input": question,
        "output": response.get("answer", ""),
        "metadata": metadata,
        "tags": [
            "venture-metrics",
            str(response.get("source_mode") or "unknown"),
            str(response.get("confidence") or "unknown"),
        ],
    }
    if session_external_id:
        kwargs["session_id"] = session_external_id
    update_current_trace(**kwargs)


def _export_steps(root: Any, trace: list[Any]) -> None:
    for index, step in enumerate(trace, start=1):
        if not isinstance(step, dict):
            continue
        name = str(step.get("decision") or step.get("phase") or f"step_{index}")
        as_type = _observation_type(step)
        with root.start_as_current_observation(as_type=as_type, name=name) as observation:
            observation.update(
                input={
                    "phase": step.get("phase"),
                    "tool": step.get("tool"),
                },
                output=step.get("observation") or {},
                metadata={
                    "step": step.get("step") or index,
                    "decision": step.get("decision"),
                    "reason": step.get("reason"),
                },
            )


def _export_retrieval(root: Any, name: str, results: list[Any]) -> None:
    if not results:
        return
    with root.start_as_current_observation(as_type="retriever", name=name) as observation:
        observation.update(
            input={"result_count": len(results)},
            output=[_compact_result(result) for result in results[:10] if isinstance(result, dict)],
            metadata={"result_count": len(results)},
        )


def _export_citations(root: Any, citations: list[Any]) -> None:
    if not citations:
        return
    with root.start_as_current_observation(as_type="event", name="answer_citations") as observation:
        observation.update(
            output=[_compact_result(citation) for citation in citations[:10] if isinstance(citation, dict)],
            metadata={"citation_count": len(citations)},
        )


def _observation_type(step: dict[str, Any]) -> str:
    phase = str(step.get("phase") or "")
    tool = step.get("tool")
    if tool:
        return "tool"
    if phase == "verify":
        return "evaluator"
    if phase == "plan":
        return "chain"
    return "span"


def _compact_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": result.get("title"),
        "url": result.get("url"),
        "source_type": result.get("source_type"),
        "reliability": result.get("reliability"),
        "score": result.get("score"),
        "snippet": result.get("snippet"),
    }


def _env(key: str, env_values: dict[str, str], *, default: str | None = None) -> str:
    return os.environ.get(key) or env_values.get(key) or default or ""


def _read_env_file(env_path: str | Path) -> dict[str, str]:
    path = Path(env_path)
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _float_or_none(value: str) -> float | None:
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None
