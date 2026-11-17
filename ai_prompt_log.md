# AI prompt log and code audit

## Initial AI coding prompt

> Build a Python 3.11+ commercial-invoice extractor from PDF and HTML with nested Pydantic v2 InvoiceExtraction and LineItem models; use OpenAI-native JSON schema, enforce invoice arithmetic, retry failed validation with reflection prompts including errors, use json-repair and a dead-letter queue, provide Streamlit interface and pytest tests. Keep the code split across schemas.py, extractor.py, and fallback.py.

## Initial candidate and human review

The following short snippets illustrate weaknesses identified during drafting and explicitly corrected in the final implementation. They are **initial candidate code examples**, not a claim that these code lines remain in the finished files. The final repository contains the corrected implementation and reproducible tests.

### Issue 1: Non-deterministic floating-point reconciliation

Initial candidate:

```python
if sum(item.line_total for item in invoice.line_items) + invoice.tax_amount != invoice.total_amount:
    raise ValueError("mismatch")
```

**Problem:** binary floating point arithmetic may reject valid penny totals. It also fails to check whether subtotal itself matches the item sum.

Corrected in `src/schemas.py`:

```python
items_total = sum((item.line_total for item in self.line_items), Decimal("0.00"))
if abs(items_total - self.subtotal) > Decimal("0.02"):
    raise ValueError("subtotal does not match sum of line items")
if abs(self.subtotal + self.tax_amount - self.total_amount) > Decimal("0.02"):
    raise ValueError("total_amount does not match subtotal + tax_amount")
```

### Issue 2: Unbounded reflection context

Initial candidate:

```python
correction = f"Document: {raw_text}\nInvalid JSON: {bad_json}\nError: {error}"
```

**Problem:** each retry could re-submit an arbitrarily large multi-page document and waste tokens.

Corrected in `src/fallback.py`:

```python
f"SOURCE (truncated):\n{raw_text[:5000]}\n\n"
f"PREVIOUS JSON (truncated):\n{bad_json[:3000]}\n\n"
f"VALIDATION ERRORS:\n{validation_summary(error)[:2000]}"
```

### Issue 3: Unsafe fallback bypassing schema validation

Initial candidate:

```python
try:
    return InvoiceExtraction.model_validate(payload)
except ValidationError:
    return payload  # bad: unvalidated object escapes
```

**Problem:** downstream users could receive malformed amounts, missing fields, or non-reconciling invoices with no failure flag.

Corrected in `src/extractor.py`: `repaired_json` repairs JSON syntax, then `InvoiceExtraction.model_validate(payload)` is still required. If it fails, `send_to_dlq` records the failure and `DLQ_FAILED` is returned. The raw unvalidated data never becomes successful output.

## Additional audit checks

- Pydantic v2: uses `@field_validator`, `@model_validator`, and `.model_dump()` / `.model_dump_json()`; no v1 decorators.
- Dates: `12th of Oct, 2024` is normalized before Pydantic date parsing.
- Currency: only `USD`, `EUR`, or `GBP` permitted, plus non-negative totals and positive integer quantities.
- Structured decoding: OpenAI SDK `chat.completions.parse(..., response_format=InvoiceDraft)` provides the native schema stage; strict `InvoiceExtraction` is applied afterward for business logic.
- Errors: upstream SDK exception bodies are not shown in the UI; never commit `.env`.
- Reflection: at most three provider attempts, with exact Pydantic `loc` and `msg` details in the corrective prompt.
- Demo: checkbox `Demo: inject first-attempt validation error` is an explicitly labeled demonstration injection, not an actual provider mistake.
- Privacy: the DLQ stores source text and model payload locally. Avoid real confidential documents in the demo; redact if needed in any deployed system.

## Verification

Run `uv run pytest -v`. The suite covers golden PDF, schema constraints, reconciliation, HTML ingestion, date normalization, invalid currency, reflection recovery, bounded prompts, failure routing, and disabling reflection.
