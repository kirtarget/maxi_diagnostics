from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _reject_constant(_: str) -> None:
    raise ValueError("json_nonfinite_number")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("json_duplicate_key")
        result[key] = value
    return result


def loads_strict(payload: str | bytes) -> Any:
    return json.loads(
        payload,
        object_pairs_hook=_unique_object,
        parse_constant=_reject_constant,
    )


def load_json_file(path: Path, *, max_bytes: int) -> Any:
    with path.open("rb") as stream:
        payload = stream.read(max_bytes + 1)
    if len(payload) > max_bytes:
        raise ValueError("json_file_too_large")
    try:
        return loads_strict(payload.decode("utf-8"))
    except ValueError as exc:
        if str(exc) in {"json_duplicate_key", "json_nonfinite_number"}:
            raise
        raise ValueError("json_invalid") from None
    except (UnicodeError, RecursionError):
        raise ValueError("json_invalid") from None
