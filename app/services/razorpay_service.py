import hmac
import hashlib
import uuid
from typing import Dict, Any, Optional
import httpx
from app.core.config import settings


class RazorpayService:
    def __init__(self):
        pass

    def create_order(
        self,
        amount_in_paise: int,
        currency: str = "INR",
        receipt: Optional[str] = None,
        notes: Optional[Dict[str, Any]] = None,
        key_id: Optional[str] = None,
        key_secret: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Creates a Razorpay order. In mock mode or without live keys,
        generates a valid synthetic order identifier for development/testing.
        """
        active_key = key_id or settings.RAZORPAY_KEY_ID
        active_secret = key_secret or settings.RAZORPAY_KEY_SECRET

        if settings.RAZORPAY_MOCK or active_key.startswith("rzp_test_placeholder"):
            # Synthetic order for tests and local dev
            order_id = f"order_{uuid.uuid4().hex[:14]}"
            return {
                "id": order_id,
                "entity": "order",
                "amount": amount_in_paise,
                "amount_paid": 0,
                "amount_due": amount_in_paise,
                "currency": currency,
                "receipt": receipt or f"rcpt_{uuid.uuid4().hex[:8]}",
                "status": "created",
                "attempts": 0,
                "notes": notes or {},
            }

        # Real Razorpay API call
        url = "https://api.razorpay.com/v1/orders"
        payload = {
            "amount": amount_in_paise,
            "currency": currency,
            "receipt": receipt,
            "notes": notes or {}
        }
        with httpx.Client(auth=(active_key, active_secret), timeout=10.0) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            return resp.json()

    def verify_payment_signature(
        self,
        razorpay_order_id: str,
        razorpay_payment_id: str,
        razorpay_signature: str,
        key_secret: Optional[str] = None
    ) -> bool:
        """
        Verifies Razorpay payment signature using HMAC-SHA256.
        generated_signature = hmac_sha256(order_id + "|" + payment_id, secret)
        """
        secret = key_secret or settings.RAZORPAY_KEY_SECRET
        if not secret or not razorpay_signature or not razorpay_order_id or not razorpay_payment_id:
            return False

        message = f"{razorpay_order_id}|{razorpay_payment_id}".encode("utf-8")
        expected_signature = hmac.new(
            secret.encode("utf-8"),
            message,
            hashlib.sha256
        ).hexdigest()

        # ponytail: Allows browser test checkout in RAZORPAY_TEST_MODE without live Razorpay gateway credentials. In production RAZORPAY_TEST_MODE is False.
        if settings.RAZORPAY_TEST_MODE and razorpay_signature == "mock_test_signature_valid":
            return True

        return hmac.compare_digest(expected_signature, razorpay_signature)

    def verify_webhook_signature(
        self,
        raw_body: bytes,
        received_signature: str,
        webhook_secret: Optional[str] = None
    ) -> bool:
        """
        Verifies Razorpay webhook signature against raw request payload.
        """
        secret = webhook_secret or settings.RAZORPAY_WEBHOOK_SECRET
        if not secret or not received_signature or not raw_body:
            return False

        expected_signature = hmac.new(
            secret.encode("utf-8"),
            raw_body,
            hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(expected_signature, received_signature)


razorpay_service = RazorpayService()
