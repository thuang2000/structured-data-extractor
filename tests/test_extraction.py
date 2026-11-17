import copy
from decimal import Decimal
from pathlib import Path
import pytest
from pydantic import ValidationError

from src.extractor import SchemaExtractor, document_text
from src.schemas import InvoiceExtraction

ROOT = Path(__file__).resolve().parents[1]


def test_golden_pdf_first_attempt(tmp_path, fake_responder):
    text = document_text((ROOT / "samples/invoice_messy.pdf").read_bytes(), "pdf")
    assert "INV-2026-104" in text
    result = SchemaExtractor(responder=fake_responder, dlq_dir=tmp_path).extract_with_retry(text)
    assert result.execution_status == "SUCCESS"
    assert result.attempts_used == 1
    assert result.error_log == []
    assert result.validated_data.total_amount == Decimal("162.00")


def test_invalid_quantity_and_negative_total(valid_invoice):
    bad = copy.deepcopy(valid_invoice)
    bad["line_items"][0]["quantity"] = 0
    with pytest.raises(ValidationError):
        InvoiceExtraction.model_validate(bad)
    bad = copy.deepcopy(valid_invoice)
    bad["total_amount"] = "-2.00"
    with pytest.raises(ValidationError):
        InvoiceExtraction.model_validate(bad)


def test_cross_field_reconciliation(valid_invoice):
    bad = copy.deepcopy(valid_invoice)
    bad["total_amount"] = "999.00"
    with pytest.raises(ValidationError, match="total_amount"):
        InvoiceExtraction.model_validate(bad)


def test_html_ingestion():
    html = (ROOT / "samples/vendor_contract.html").read_text(encoding="utf-8")
    clean = document_text(html, "html")
    assert "Northstar Office Supplies" in clean
    assert "<html>" not in clean


def test_date_and_money_normalization(valid_invoice):
    valid_invoice["invoice_date"] = "12th of Oct, 2024"
    valid_invoice["total_amount"] = "$162.00"
    invoice = InvoiceExtraction.model_validate(valid_invoice)
    assert str(invoice.invoice_date) == "2024-10-12"
    assert invoice.total_amount == Decimal("162.00")


def test_invalid_currency(valid_invoice):
    valid_invoice["currency"] = "CAD"
    with pytest.raises(ValidationError):
        InvoiceExtraction.model_validate(valid_invoice)
