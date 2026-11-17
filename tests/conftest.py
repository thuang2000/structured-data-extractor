import json
import pytest

@pytest.fixture
def valid_invoice():
    return {
        "invoice_number": "INV-2026-104", "vendor_name": "Northstar Office Supplies",
        "invoice_date": "November 10, 2026",
        "line_items": [
            {"description": "Notebook cases", "quantity": 2, "unit_price": "$45.00", "line_total": "90.00"},
            {"description": "Desk organizer", "quantity": 3, "unit_price": "20.00", "line_total": "60.00"},
        ],
        "subtotal": "150.00", "tax_amount": "12.00", "total_amount": "162.00", "currency": "USD",
    }

@pytest.fixture
def fake_responder(valid_invoice):
    return lambda source, correction: json.dumps(valid_invoice)
