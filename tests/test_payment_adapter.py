"""Unit and integration tests for Payment Gateway Adapter — EDD Step 10.

Tests typed contracts (PaymentLinkResult, InvoiceStatusResult), MockPaymentAdapter,
RazorpayPaymentAdapter (amount conversion to paise, basic auth, error mapping),
and factory provider switching.
"""

import os
from unittest.mock import MagicMock, patch
import pytest

from payment_adapter import (
    PaymentGatewayAdapter,
    PaymentLinkResult,
    InvoiceStatusResult,
    MockPaymentAdapter,
    RazorpayPaymentAdapter,
    PaymentGatewayError,
    get_payment_adapter,
)


def test_payment_link_result_contract():
    """Verify PaymentLinkResult adheres to typed contract and serialization."""
    res = PaymentLinkResult(
        link_id="plink_12345",
        short_url="https://rzp.io/i/testlink",
        amount=5000.0,
        currency="INR",
        status="created",
        raw_response={"id": "plink_12345", "amount": 500000}
    )
    assert res.link_id == "plink_12345"
    assert res.short_url == "https://rzp.io/i/testlink"
    assert res.amount == 5000.0
    assert res.currency == "INR"
    assert res.status == "created"


def test_invoice_status_result_contract():
    """Verify InvoiceStatusResult adheres to typed contract."""
    res = InvoiceStatusResult(
        invoice_id="inv_12345",
        status="paid",
        amount_due=0.0,
        amount_paid=15000.0,
        raw_response={"id": "inv_12345", "status": "paid"}
    )
    assert res.invoice_id == "inv_12345"
    assert res.status == "paid"
    assert res.amount_paid == 15000.0


def test_mock_payment_adapter():
    """Verify MockPaymentAdapter produces deterministic responses offline."""
    adapter = MockPaymentAdapter()
    
    # Create payment link
    link_res = adapter.create_payment_link(
        invoice_id="INV-TEST-001",
        amount=25000.0,
        customer_phone="+919876543210",
        customer_email="test@example.com",
        description="Payment for INV-TEST-001"
    )
    assert isinstance(link_res, PaymentLinkResult)
    assert link_res.amount == 25000.0
    assert link_res.status == "created"
    assert "rzp.io" in link_res.short_url

    # Check status
    status_res = adapter.fetch_invoice_status("INV-TEST-001")
    assert isinstance(status_res, InvoiceStatusResult)
    assert status_res.invoice_id == "INV-TEST-001"
    assert status_res.status in ["created", "issued", "paid", "partially_paid"]


def test_razorpay_adapter_request_structure():
    """Verify RazorpayPaymentAdapter maps amounts to paise, uses basic auth, and formats request."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "id": "plink_live_mock_123",
        "short_url": "https://rzp.io/i/mocktest",
        "amount": 5000000,  # 50,000 INR in paise
        "currency": "INR",
        "status": "created"
    }

    with patch("requests.post", return_value=mock_resp) as mock_post:
        adapter = RazorpayPaymentAdapter(
            key_id="dummy_rzp_key",
            key_secret="dummy_rzp_secret"
        )
        
        res = adapter.create_payment_link(
            invoice_id="INV-001",
            amount=50000.0,
            customer_phone="9876543210",
            customer_email="customer@example.com",
            description="Recovery for INV-001"
        )

        assert res.link_id == "plink_live_mock_123"
        assert res.amount == 50000.0
        assert res.short_url == "https://rzp.io/i/mocktest"
        
        # Verify call arguments
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        
        # Check basic auth
        assert call_args[1]["auth"] == ("dummy_rzp_key", "dummy_rzp_secret")
        
        # Check payload: amount must be converted to paise (50000 * 100 = 5000000)
        json_data = call_args[1]["json"]
        assert json_data["amount"] == 5000000
        assert json_data["currency"] == "INR"
        assert json_data["customer"]["contact"] == "9876543210"
        assert json_data["notes"]["invoice_id"] == "INV-001"


def test_razorpay_adapter_error_handling():
    """Verify RazorpayPaymentAdapter raises PaymentGatewayError on API failure."""
    mock_resp = MagicMock()
    mock_resp.status_code = 400
    mock_resp.text = '{"error": {"code": "BAD_REQUEST_ERROR", "description": "Invalid contact number"}}'
    mock_resp.json.return_value = {"error": {"code": "BAD_REQUEST_ERROR", "description": "Invalid contact number"}}

    with patch("requests.post", return_value=mock_resp):
        adapter = RazorpayPaymentAdapter(
            key_id="dummy_rzp_key",
            key_secret="dummy_rzp_secret"
        )
        with pytest.raises(PaymentGatewayError) as exc_info:
            adapter.create_payment_link(
                invoice_id="INV-001",
                amount=100.0,
                customer_phone="invalid_phone"
            )
        assert "BAD_REQUEST_ERROR" in str(exc_info.value) or "400" in str(exc_info.value)


def test_payment_adapter_factory_and_switching():
    """Verify get_payment_adapter switches provider based on environment config."""
    with patch.dict(os.environ, {"PAYMENT_GATEWAY_PROVIDER": "mock"}):
        adapter = get_payment_adapter()
        assert isinstance(adapter, MockPaymentAdapter)

    with patch.dict(os.environ, {
        "PAYMENT_GATEWAY_PROVIDER": "razorpay",
        "RAZORPAY_KEY_ID": "dummy_key",
        "RAZORPAY_KEY_SECRET": "dummy_secret"
    }):
        adapter = get_payment_adapter()
        assert isinstance(adapter, RazorpayPaymentAdapter)
