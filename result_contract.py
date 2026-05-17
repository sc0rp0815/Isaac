from __future__ import annotations

from typing import Any

REQUIRED_FIELDS = ("ok", "output", "error", "metadata")
OPTIONAL_FIELDS = ("queue_id", "audit_id")


def _as_metadata(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    return {"raw_metadata": value} if value is not None else {}


def error_result(error: str, *, metadata: dict[str, Any] | None = None, queue_id: str = "", audit_id: str = "") -> dict[str, Any]:
    result = {
        "ok": False,
        "output": None,
        "error": str(error or "unknown_error"),
        "metadata": _as_metadata(metadata),
    }
    if queue_id:
        result["queue_id"] = queue_id
    if audit_id:
        result["audit_id"] = audit_id
    return result


def normalize_result(raw: Any, *, default_output: Any = None, source: str = "") -> dict[str, Any]:
    if isinstance(raw, dict):
        ok = bool(raw.get("ok"))
        output = raw.get("output", raw.get("content", default_output))
        error = str(raw.get("error", ""))
        metadata = _as_metadata(raw.get("metadata"))
        for key in ("status_code", "via", "url", "source", "kind"):
            if key in raw and key not in metadata:
                metadata[key] = raw.get(key)
        if source:
            metadata.setdefault("source", source)
        normalized = {"ok": ok, "output": output, "error": error, "metadata": metadata}
        for optional in OPTIONAL_FIELDS:
            if optional in raw and raw.get(optional):
                normalized[optional] = raw.get(optional)
                metadata.setdefault(optional, raw.get(optional))
        if not ok and not error:
            normalized["error"] = "tool_execution_failed"
        return normalized

    return error_result("invalid_tool_result_type", metadata={"source": source, "raw_type": type(raw).__name__})


def ensure_result_contract(raw: Any, *, source: str = "") -> dict[str, Any]:
    normalized = normalize_result(raw, source=source)
    for field in REQUIRED_FIELDS:
        if field not in normalized:
            return error_result("invalid_tool_result_contract", metadata={"missing_field": field, "source": source})
    if not isinstance(normalized.get("metadata"), dict):
        return error_result("invalid_tool_result_contract", metadata={"reason": "metadata_not_dict", "source": source})
    return normalized
