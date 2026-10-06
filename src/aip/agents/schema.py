"""Convert Pydantic output models into JSON Schemas that structured outputs accept.

Structured outputs require `additionalProperties: false` and every property in `required`
(optional fields become nullable), and reject numeric/string constraints. Unsupported
keywords are dropped here; Pydantic still enforces them when the response is validated.
"""

from typing import Any

from pydantic import BaseModel

_KEEP = {
    "type",
    "properties",
    "required",
    "items",
    "enum",
    "const",
    "anyOf",
    "allOf",
    "$ref",
    "$defs",
    "description",
    "additionalProperties",
    "format",
}
_FORMATS = {"date-time", "time", "date", "duration", "email", "hostname", "uri", "uuid"}


def _clean(node: Any) -> Any:
    if isinstance(node, list):
        return [_clean(n) for n in node]
    if not isinstance(node, dict):
        return node
    out: dict[str, Any] = {}
    for key, value in node.items():
        if key not in _KEEP:
            continue
        if key == "format" and value not in _FORMATS:
            continue
        if key in ("properties", "$defs"):
            out[key] = {name: _clean(sub) for name, sub in value.items()}
        else:
            out[key] = _clean(value)
    if out.get("type") == "object" and "properties" in out:
        out["additionalProperties"] = False
        out["required"] = list(out["properties"])
    return out


def output_schema(model: type[BaseModel]) -> dict[str, Any]:
    return _clean(model.model_json_schema(mode="validation"))
