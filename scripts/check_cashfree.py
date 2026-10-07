"""
Checks that the Cashfree keys in the environment (or .env) work, by creating a small test
order and then reading its payments back. No money moves: the order is never paid and
simply expires.

    python -m scripts.check_cashfree                 # uses CASHFREE_ENVIRONMENT (default sandbox)
    python -m scripts.check_cashfree --amount 1
"""
import argparse
import sys
import uuid

import httpx

from app.core.config import settings
from app.services.cashfree_service import cashfree_service


def main() -> int:
    parser = argparse.ArgumentParser(description="Check the Cashfree keys with a test order.")
    parser.add_argument("--amount", type=float, default=1.0, help="Test order amount in INR (default 1).")
    args = parser.parse_args()

    app_id = settings.CASHFREE_APP_ID
    secret_key = settings.CASHFREE_SECRET_KEY
    environment = settings.CASHFREE_ENVIRONMENT

    if not app_id or not secret_key:
        print("FAIL: CASHFREE_APP_ID or CASHFREE_SECRET_KEY is empty.")
        return 1
    if settings.CASHFREE_MOCK:
        print("WARN: CASHFREE_MOCK=true, so the app treats every order as paid. Set it to false to use real keys.")
        settings.CASHFREE_MOCK = False  # still check the keys against Cashfree below

    print(f"Environment: {environment}  |  App ID: {app_id[:6]}...")

    order_id = f"check_{uuid.uuid4().hex[:16]}"
    customer = {
        "customer_id": "keycheck",
        "customer_phone": "9999999999",
        "customer_email": "keycheck@example.com",
    }
    try:
        order = cashfree_service.create_order(
            order_id, args.amount, customer, app_id, secret_key, environment
        )
    except httpx.HTTPStatusError as e:
        print(f"FAIL: create order -> HTTP {e.response.status_code}: {e.response.text}")
        if e.response.status_code == 401:
            print("Hint: wrong keys, or sandbox keys used with production (or the other way round).")
        return 1
    except httpx.HTTPError as e:
        print(f"FAIL: could not reach Cashfree: {e}")
        return 1

    if not order.get("payment_session_id"):
        print(f"FAIL: order created but no payment_session_id returned: {order}")
        return 1
    print(f"OK: order {order['order_id']} created (status {order.get('order_status')}).")

    try:
        payment = cashfree_service.get_successful_payment(order_id, app_id, secret_key, environment)
    except httpx.HTTPError as e:
        print(f"FAIL: reading payments: {e}")
        return 1
    print(f"OK: payments read back (paid: {'yes' if payment else 'no, as expected'}).")

    print("All good: the Cashfree keys work.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
