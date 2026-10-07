import base64
import hmac
import hashlib
import re
import time
import uuid
from typing import Dict, Any, List, Optional
import httpx
from app.core.config import settings

BASE_URLS = {
    "sandbox": "https://sandbox.cashfree.com/pg",
    "production": "https://api.cashfree.com/pg",
}

# Webhooks older than this are rejected as possible replays
WEBHOOK_MAX_AGE_SECONDS = 5 * 60


def normalize_indian_phone(phone: Optional[str]) -> Optional[str]:
    """
    Reduces a stored phone number ("+91 98765-43210", "098765 43210") to the 10-digit
    mobile number Cashfree accepts. Returns None if it is not a valid Indian mobile number.
    """
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    return digits if re.fullmatch(r"[6-9]\d{9}", digits) else None


class CashfreeService:
    def _headers(self, app_id: str, secret_key: str) -> Dict[str, str]:
        return {
            "x-client-id": app_id,
            "x-client-secret": secret_key,
            "x-api-version": settings.CASHFREE_API_VERSION,
            "Content-Type": "application/json",
        }

    def _base_url(self, environment: str) -> str:
        return BASE_URLS["production" if environment == "production" else "sandbox"]

    def is_mock(self) -> bool:
        return settings.CASHFREE_MOCK

    def create_order(
        self,
        order_id: str,
        amount: float,
        customer: Dict[str, str],
        app_id: str,
        secret_key: str,
        environment: str,
        currency: str = "INR",
        tags: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Creates a Cashfree PG order and returns it (including payment_session_id).
        In mock mode, returns a synthetic order for development/testing.
        """
        if self.is_mock():
            return {
                "order_id": order_id,
                "cf_order_id": None,
                "order_amount": amount,
                "order_currency": currency,
                "order_status": "ACTIVE",
                "payment_session_id": f"session_mock_{uuid.uuid4().hex}",
                "order_tags": tags or {},
            }

        payload = {
            "order_id": order_id,
            "order_amount": amount,
            "order_currency": currency,
            "customer_details": customer,
            "order_tags": tags or {},
        }
        if settings.CASHFREE_NOTIFY_URL:
            payload["order_meta"] = {"notify_url": settings.CASHFREE_NOTIFY_URL}
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(
                f"{self._base_url(environment)}/orders",
                json=payload,
                headers=self._headers(app_id, secret_key),
            )
            resp.raise_for_status()
            return resp.json()

    def get_successful_payment(
        self,
        order_id: str,
        app_id: str,
        secret_key: str,
        environment: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Asks Cashfree for the order's payments and returns the successful one, if any.
        This server-to-server check is the source of truth; the browser is never trusted.
        In mock mode every order is treated as paid.
        """
        if self.is_mock():
            return {"cf_payment_id": f"mock_{uuid.uuid4().hex[:14]}", "payment_status": "SUCCESS"}

        with httpx.Client(timeout=10.0) as client:
            resp = client.get(
                f"{self._base_url(environment)}/orders/{order_id}/payments",
                headers=self._headers(app_id, secret_key),
            )
            resp.raise_for_status()
            payments: List[Dict[str, Any]] = resp.json()

        return next((p for p in payments if p.get("payment_status") == "SUCCESS"), None)

    def verify_webhook_signature(
        self,
        raw_body: bytes,
        timestamp: str,
        received_signature: str,
        secret_key: str,
    ) -> bool:
        """
        Verifies a Cashfree webhook: base64(HMAC-SHA256(timestamp + raw_body, secret_key)).
        The timestamp must also be recent, so a captured webhook cannot be replayed later.
        """
        if not secret_key or not received_signature or not timestamp or not raw_body:
            return False
        if not self.is_fresh_timestamp(timestamp):
            return False

        message = timestamp.encode("utf-8") + raw_body
        expected_signature = base64.b64encode(
            hmac.new(secret_key.encode("utf-8"), message, hashlib.sha256).digest()
        ).decode("utf-8")

        return hmac.compare_digest(expected_signature, received_signature)

    def is_fresh_timestamp(self, timestamp: str) -> bool:
        """Cashfree sends epoch milliseconds; seconds are accepted too."""
        try:
            sent_at = int(timestamp)
        except ValueError:
            return False
        if sent_at > 10**11:
            sent_at //= 1000
        return abs(time.time() - sent_at) <= WEBHOOK_MAX_AGE_SECONDS


cashfree_service = CashfreeService()
