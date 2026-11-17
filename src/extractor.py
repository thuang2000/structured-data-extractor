"""Document ingestion, native constrained decoding, validation, reflection, and DLQ."""
import json
import os
from pathlib import Path
from typing import Callable
from io import BytesIO

from bs4 import BeautifulSoup
from pydantic import ValidationError
from pypdf import PdfReader

from src.schemas import ExtractionResult, InvoiceDraft, InvoiceExtraction
from src.fallback import build_reflection_prompt, repaired_json, send_to_dlq, validation_summary


class ExtractionProviderError(Exception):
    """Safe message for model/connection failures, without raw SDK secrets."""


def document_text(payload: bytes | str, file_type: str) -> str:
    if file_type == "pdf":
        reader = PdfReader(BytesIO(payload if isinstance(payload, bytes) else payload.encode()))
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
    elif file_type in ("html", "text"):
        raw = payload.decode("utf-8", errors="replace") if isinstance(payload, bytes) else payload
        text = BeautifulSoup(raw, "html.parser").get_text("\n", strip=True) if file_type == "html" else raw
    else:
        raise ValueError("Supported input types: pdf, html, text")
    if not text.strip():
        raise ValueError("No selectable text found. Scanned image-only PDFs need OCR first.")
    return text


class SchemaExtractor:
    def __init__(self, responder: Callable[[str, str], str] | None = None,
                 dlq_dir: str | Path = "dlq", model: str | None = None):
        self.responder = responder
        self.dlq_dir = Path(dlq_dir)
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self._client = None

    def _respond(self, source: str, correction: str) -> str:
        if self.responder is not None:
            return self.responder(source, correction)
        from openai import OpenAI
        key = os.getenv("OPENAI_API_KEY", "")
        if not key or key.startswith("your_"):
            raise ExtractionProviderError("Set OPENAI_API_KEY in .env before live extraction.")
        if self._client is None:
            self._client = OpenAI(api_key=key, timeout=30.0, max_retries=1)
        try:
            completion = self._client.chat.completions.parse(
                model=self.model,
                response_format=InvoiceDraft,
                messages=[
                    {"role": "system", "content": (
                        "Extract exactly one commercial invoice. Return JSON matching the schema. "
                        "Keep dates and monetary values as source strings. "
                        "Never invent information. If a field is missing, supply an empty string "
                        "so the downstream validator can report it. Extract all line items.")},
                    {"role": "user", "content": source[:10000] + ("\n\n" + correction if correction else "")},
                ],
            )
            message = completion.choices[0].message
            if message.parsed is None:
                raise ExtractionProviderError("The provider returned no usable structured extraction.")
            return message.parsed.model_dump_json()
        except ExtractionProviderError:
            raise
        except Exception as exc:
            # Do not display upstream errors; SDK messages can contain sensitive data.
            raise ExtractionProviderError("Model request failed. Check the API key, balance, network, and selected model.") from None

    def extract_with_retry(self, raw_text: str, max_retries: int = 3,
                           reflection_enabled: bool = True,
                           simulate_first_error: bool = False,
                           on_event: Callable[[str], None] | None = None) -> ExtractionResult:
        if max_retries < 1:
            raise ValueError("max_retries must be at least 1")
        if not raw_text.strip():
            raise ValueError("Document text is empty")
        error_log: list[str] = []
        corrective_prompts: list[str] = []
        events: list[str] = []
        def record(message: str) -> None:
            events.append(message)
            if on_event is not None:
                on_event(message)

        last_json = ""
        correction = ""
        used = 0

        for attempt in range(1, max_retries + 1):
            if attempt > 1 and not reflection_enabled:
                break
            used = attempt
            record(f"Attempt {attempt}: provider-native structured output requested")
            last_json = self._respond(raw_text, correction)
            try:
                data = json.loads(last_json)
                if simulate_first_error and attempt == 1:
                    # Explicitly labeled demonstration injection, never represented as a real model error.
                    data["total_amount"] = "999999.00"
                    last_json = json.dumps(data)
                    record("Demo injection: changed total_amount to cause a validation error")
                invoice = InvoiceExtraction.model_validate(data)
                record("Pydantic validation and reconciliation passed")
                return ExtractionResult(
                    validated_data=invoice, attempts_used=attempt,
                    error_log=error_log, corrective_prompts=corrective_prompts,
                    execution_status="SUCCESS" if attempt == 1 else "REPAIRED_VIA_REFLECTION",
                    events=events,
                )
            except (ValidationError, ValueError, json.JSONDecodeError) as exc:
                summary = validation_summary(exc)
                error_log.append(f"Attempt {attempt}: {summary}")
                record(f"Attempt {attempt}: Pydantic validation failed")
                if attempt < max_retries and reflection_enabled:
                    correction = build_reflection_prompt(raw_text, last_json, exc)
                    corrective_prompts.append(correction)
                    record("Prepared corrective reflection prompt")

        record("Fallback: heuristic JSON syntax repair and re-validation")
        try:
            payload = repaired_json(last_json)
            invoice = InvoiceExtraction.model_validate(payload)
            record("Heuristic repair passed strict validation")
            return ExtractionResult(
                validated_data=invoice, attempts_used=used,
                error_log=error_log, corrective_prompts=corrective_prompts,
                execution_status="REPAIRED_VIA_REFLECTION", events=events,
            )
        except (ValueError, ValidationError, TypeError, ImportError) as exc:
            error_log.append("Heuristic fallback: " + validation_summary(exc))
            destination = send_to_dlq(raw_text, last_json, error_log, self.dlq_dir)
            record("Failed document routed to Dead-Letter Queue for human review")
            return ExtractionResult(
                attempts_used=used, error_log=error_log,
                corrective_prompts=corrective_prompts, execution_status="DLQ_FAILED",
                dlq_path=str(destination), events=events,
            )
