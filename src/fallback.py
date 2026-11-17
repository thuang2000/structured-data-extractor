"""Reflection prompts, heuristic JSON repair, and failed-document routing."""
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from pydantic import ValidationError


def validation_summary(error: Exception) -> str:
    if isinstance(error, ValidationError):
        return "\n".join(
            f"field={'.'.join(map(str, item['loc'])) or 'invoice'}, error={item['msg']}"
            for item in error.errors(include_url=False)
        )
    return str(error)


def build_reflection_prompt(raw_text: str, bad_json: str, error: Exception) -> str:
    """Bound retry prompt length; include precise validation locations and errors."""
    return (
        "Fix the invoice JSON based on these Pydantic validation failures. "
        "Use only facts in the source document; do not invent missing values.\n\n"
        f"SOURCE (truncated):\n{raw_text[:5000]}\n\n"
        f"PREVIOUS JSON (truncated):\n{bad_json[:3000]}\n\n"
        f"VALIDATION ERRORS:\n{validation_summary(error)[:2000]}"
    )


def repaired_json(raw: str) -> object:
    """Repair syntax only, never bypass strict business validation."""
    from json_repair import repair_json
    return json.loads(repair_json(raw))


def send_to_dlq(raw_text: str, last_payload: str, errors: list[str], folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    destination = folder / f"failed_{uuid4().hex}.json"
    record = {
        "status": "DLQ_FAILED",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "raw_text": raw_text[:10000],
        "last_payload": last_payload[:10000],
        "errors": errors,
    }
    destination.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return destination
