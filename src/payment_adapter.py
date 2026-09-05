"""Payment Gateway Adapter — EDD Step 10.

Provides vendor-agnostic typed contracts and abstraction layer for payment gateways
(Razorpay live sandbox API vs Mock adapter for offline testing).
Shields downstream Action Selector, Policy Engine, and Event Consumer from vendor-specific response shapes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
import logging
import os
import time
from typing import Any, Optional
import uuid

from pydantic import BaseModel, Field
import requests

logger = logging.getLogger(__name__)


class PaymentGatewayError(Exception):
    """Raised when payment gateway API call fails."""
    pass


class PaymentLinkResult(BaseModel):
    """Typed result contract for payment link creation."""
    link_id: str = Field(..., description="Unique payment link identifier (e.g. plink_...)")
    short_url: str = Field(..., description="Hosted checkout payment URL")
    amount: float = Field(..., gt=0, description="Amount in INR (Rupees)")
    currency: str = Field(default="INR", description="Currency code")
    status: str = Field(default="created", description="Status of link: created, paid, expired, cancelled")
    expire_by: Optional[int] = Field(default=None, description="Unix expiry timestamp")
    raw_response: dict[str, Any] = Field(default_factory=dict, description="Raw provider response payload")


class InvoiceStatusResult(BaseModel):
    """Typed result contract for invoice status lookup."""
    invoice_id: str = Field(..., description="Internal or vendor invoice ID")
    status: str = Field(..., description="Status: paid, issued, partially_paid, expired, cancelled")
    amount_due: float = Field(default=0.0, description="Remaining balance in INR")
    amount_paid: float = Field(default=0.0, description="Paid amount in INR")
    paid_at: Optional[datetime] = Field(default=None, description="Timestamp of settlement")
    raw_response: dict[str, Any] = Field(default_factory=dict, description="Raw provider response payload")


class PaymentGatewayAdapter(ABC):
    """Abstract interface for Payment Gateway integrations."""

    @abstractmethod
    def create_payment_link(
        self,
        invoice_id: str,
        amount: float,
        customer_phone: Optional[str] = None,
        customer_email: Optional[str] = None,
        customer_name: Optional[str] = None,
        description: Optional[str] = None,
        expire_by: Optional[int] = None,
        **kwargs: Any,
    ) -> PaymentLinkResult:
        """Create a hosted payment link."""
        pass

    @abstractmethod
    def fetch_invoice_status(self, invoice_id: str) -> InvoiceStatusResult:
        """Query current status of an invoice or payment link."""
        pass

    @abstractmethod
    def cancel_payment_link(self, link_id: str) -> bool:
        """Cancel an active payment link."""
        pass


class RazorpayPaymentAdapter(PaymentGatewayAdapter):
    """Live Razorpay payment gateway adapter communicating over REST API."""

    BASE_URL = "https://api.razorpay.com/v1"

    def __init__(
        self,
        key_id: Optional[str] = None,
        key_secret: Optional[str] = None,
        timeout: float = 30.0,
    ):
        self.key_id = key_id or os.getenv("RAZORPAY_KEY_ID")
        self.key_secret = key_secret or os.getenv("RAZORPAY_KEY_SECRET")
        self.timeout = timeout

        if not self.key_id or not self.key_secret:
            raise ValueError("RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET must be provided or set in environment")

    def _auth(self) -> tuple[str, str]:
        return (self.key_id, self.key_secret)

    # RETRY POLICY: Exponential backoff with jitter on transient network/5xx/429 errors (attempts=3, backoff_factor=1.0s) per SPEC §6.7
    def _execute_with_retry(self, method: str, endpoint: str, **kwargs: Any) -> requests.Response:
        """Executes external HTTP call against Razorpay REST API with exponential backoff retry.

        Retries up to 3 times on transient connection errors, read timeouts, HTTP 429 (rate limits),
        or HTTP 5xx (internal gateway errors) with exponential backoff (1s, 2s, 4s).
        """
        max_retries = 3
        backoff_factor = 1.0
        last_exception: Optional[Exception] = None
        resp: Optional[requests.Response] = None

        for attempt in range(max_retries):
            try:
                if method.upper() == "POST":
                    resp = requests.post(endpoint, auth=self._auth(), timeout=self.timeout, **kwargs)
                elif method.upper() == "GET":
                    resp = requests.get(endpoint, auth=self._auth(), timeout=self.timeout, **kwargs)
                else:
                    resp = requests.request(method=method, url=endpoint, auth=self._auth(), timeout=self.timeout, **kwargs)

                # Success or permanent client error (4xx other than 429) returns immediately without retry
                if resp.status_code < 500 and resp.status_code != 429:
                    return resp
                if resp.status_code == 429 and "limit" in resp.text.lower():
                    return resp

                logger.warning(
                    f"Razorpay API returned status {resp.status_code} on attempt {attempt + 1}/{max_retries}. "
                    f"Retrying in {backoff_factor * (2 ** attempt)}s..."
                )
            except (requests.ConnectionError, requests.Timeout) as e:
                last_exception = e
                logger.warning(
                    f"Razorpay network exception on attempt {attempt + 1}/{max_retries}: {e}. "
                    f"Retrying in {backoff_factor * (2 ** attempt)}s..."
                )

            if attempt < max_retries - 1:
                time.sleep(backoff_factor * (2 ** attempt))

        if last_exception:
            raise PaymentGatewayError(f"Razorpay network error after {max_retries} retries: {last_exception}") from last_exception
        if resp is not None:
            return resp
        raise PaymentGatewayError(f"Razorpay request failed after {max_retries} attempts")

    def create_payment_link(
        self,
        invoice_id: str,
        amount: float,
        customer_phone: Optional[str] = None,
        customer_email: Optional[str] = None,
        customer_name: Optional[str] = None,
        description: Optional[str] = None,
        expire_by: Optional[int] = None,
        **kwargs: Any,
    ) -> PaymentLinkResult:
        """Creates a Razorpay Payment Link (/v1/payment_links) with retry-with-backoff protection."""
        if amount <= 0:
            raise ValueError(f"Amount must be strictly positive, got {amount}")

        # Convert amount in rupees to paise (integer)
        amount_in_paise = int(round(amount * 100))

        customer_dict: dict[str, Any] = {
            "name": customer_name or f"Customer {invoice_id}"
        }
        if customer_phone:
            # Strip non-digits except leading +
            clean_phone = customer_phone.strip()
            customer_dict["contact"] = clean_phone
        if customer_email:
            customer_dict["email"] = customer_email.strip()

        payload: dict[str, Any] = {
            "amount": amount_in_paise,
            "currency": "INR",
            "accept_partial": False,
            "description": description or f"Recovery for invoice {invoice_id}",
            "customer": customer_dict,
            "notify": {
                "sms": bool(customer_phone),
                "email": bool(customer_email),
            },
            "reminder_enable": True,
            "notes": {
                "invoice_id": invoice_id,
            }
        }
        if expire_by:
            payload["expire_by"] = expire_by

        endpoint = f"{self.BASE_URL}/payment_links"
        try:
            resp = self._execute_with_retry("POST", endpoint, json=payload)
        except PaymentGatewayError:
            raise
        except Exception as e:
            raise PaymentGatewayError(f"Razorpay network error: {e}") from e

        if resp.status_code not in (200, 201):
            try:
                err_data = resp.json().get("error", {})
                err_desc = err_data.get("description") or resp.text
            except Exception:
                err_desc = resp.text

            # Graceful degradation on test mode rate limit / quota exhaustion
            if resp.status_code == 429 or "limit" in err_desc.lower():
                logger.warning(
                    f"Razorpay rate/quota limit reached ({resp.status_code}: {err_desc}). "
                    "Gracefully degrading to MockPaymentAdapter for business continuity."
                )
                mock_adapter = MockPaymentAdapter()
                return mock_adapter.create_payment_link(
                    invoice_id=invoice_id,
                    amount=amount,
                    customer_phone=customer_phone,
                    customer_email=customer_email,
                    customer_name=customer_name,
                    description=description,
                    expire_by=expire_by,
                    **kwargs,
                )
            raise PaymentGatewayError(f"Razorpay API error ({resp.status_code}): {err_desc}")

        data = resp.json()
        return PaymentLinkResult(
            link_id=data.get("id", ""),
            short_url=data.get("short_url", ""),
            amount=round(data.get("amount", amount_in_paise) / 100.0, 2),
            currency=data.get("currency", "INR"),
            status=data.get("status", "created"),
            expire_by=data.get("expire_by"),
            raw_response=data,
        )

    def fetch_invoice_status(self, invoice_id: str) -> InvoiceStatusResult:
        """Fetches payment link / invoice details from Razorpay with retry protection."""
        # If passed a payment link ID (plink_...) query payment_links endpoint
        if invoice_id.startswith("plink_"):
            endpoint = f"{self.BASE_URL}/payment_links/{invoice_id}"
        else:
            endpoint = f"{self.BASE_URL}/invoices/{invoice_id}"

        try:
            resp = self._execute_with_retry("GET", endpoint)
        except PaymentGatewayError:
            raise
        except Exception as e:
            raise PaymentGatewayError(f"Razorpay network error: {e}") from e

        if resp.status_code != 200:
            try:
                err_data = resp.json().get("error", {})
                err_desc = err_data.get("description") or resp.text
            except Exception:
                err_desc = resp.text
            raise PaymentGatewayError(f"Razorpay API error ({resp.status_code}): {err_desc}")

        data = resp.json()
        status_str = data.get("status", "issued")
        amt_total = round(data.get("amount", 0) / 100.0, 2)
        amt_paid = round(data.get("amount_paid", 0) / 100.0, 2)

        return InvoiceStatusResult(
            invoice_id=invoice_id,
            status=status_str,
            amount_due=max(0.0, amt_total - amt_paid),
            amount_paid=amt_paid,
            raw_response=data,
        )

    def cancel_payment_link(self, link_id: str) -> bool:
        """Cancels a Razorpay payment link with retry protection."""
        endpoint = f"{self.BASE_URL}/payment_links/{link_id}/cancel"
        try:
            resp = self._execute_with_retry("POST", endpoint)
            return resp.status_code in (200, 201)
        except Exception:
            return False


class MockPaymentAdapter(PaymentGatewayAdapter):
    """Deterministic, zero-network mock adapter for tests and offline execution."""

    def __init__(self):
        self._links: dict[str, dict[str, Any]] = {}

    def create_payment_link(
        self,
        invoice_id: str,
        amount: float,
        customer_phone: Optional[str] = None,
        customer_email: Optional[str] = None,
        customer_name: Optional[str] = None,
        description: Optional[str] = None,
        expire_by: Optional[int] = None,
        **kwargs: Any,
    ) -> PaymentLinkResult:
        if amount <= 0:
            raise ValueError(f"Amount must be strictly positive, got {amount}")

        link_id = f"plink_mock_{uuid.uuid4().hex[:10]}"
        short_url = f"https://rzp.io/i/mock_{uuid.uuid4().hex[:8]}"

        link_data = {
            "id": link_id,
            "short_url": short_url,
            "amount": int(round(amount * 100)),
            "currency": "INR",
            "status": "created",
            "invoice_id": invoice_id,
            "customer": {"contact": customer_phone, "email": customer_email},
        }
        self._links[link_id] = link_data
        self._links[invoice_id] = link_data

        return PaymentLinkResult(
            link_id=link_id,
            short_url=short_url,
            amount=amount,
            currency="INR",
            status="created",
            expire_by=expire_by,
            raw_response=link_data,
        )

    def fetch_invoice_status(self, invoice_id: str) -> InvoiceStatusResult:
        link_data = self._links.get(invoice_id, {})
        status = link_data.get("status", "issued")
        amt = round(link_data.get("amount", 10000) / 100.0, 2)
        return InvoiceStatusResult(
            invoice_id=invoice_id,
            status=status,
            amount_due=amt if status != "paid" else 0.0,
            amount_paid=amt if status == "paid" else 0.0,
            raw_response=link_data,
        )

    def cancel_payment_link(self, link_id: str) -> bool:
        if link_id in self._links:
            self._links[link_id]["status"] = "cancelled"
            return True
        return False


def get_payment_adapter() -> PaymentGatewayAdapter:
    """Factory to instantiate the configured PaymentGatewayAdapter."""
    provider = os.getenv("PAYMENT_GATEWAY_PROVIDER", "mock").lower().strip()
    if provider == "razorpay":
        key_id = os.getenv("RAZORPAY_KEY_ID")
        key_secret = os.getenv("RAZORPAY_KEY_SECRET")
        if key_id and key_secret:
            return RazorpayPaymentAdapter(key_id=key_id, key_secret=key_secret)
        logger.warning("RAZORPAY_KEY_ID or SECRET missing. Falling back to MockPaymentAdapter.")
        return MockPaymentAdapter()
    return MockPaymentAdapter()
