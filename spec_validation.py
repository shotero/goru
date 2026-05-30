from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
SCHEMA_PATH = ROOT / "spec.schema.json"


def validate_tool_spec(spec: dict[str, Any], path: Path) -> None:
    try:
        from jsonschema import Draft202012Validator  # type: ignore[import-not-found]
    except ModuleNotFoundError as exc:
        raise ValueError("jsonschema is required to validate tool specs") from exc

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(spec), key=lambda error: list(error.path))
    if not errors:
        return

    details = []
    for error in errors[:5]:
        location = ".".join(str(part) for part in error.absolute_path) or "<root>"
        details.append(f"{location}: {error.message}")
    suffix = "" if len(errors) <= 5 else f" ({len(errors) - 5} more)"
    raise ValueError(f"{path} does not match spec.schema.json: {'; '.join(details)}{suffix}")
