"""
Exposes four functions used by the payment_tools node in agent_graph.py:
  init_razorpay_client()        → razorpay.Client (cached singleton)
  create_payment_link(...)      → dict with short_url, payment_link_id
  execute_mandate_charge(...)   → dict with razorpay_order_id, payment_id
  verify_webhook_signature(...) → bool
"""

import hashlib
import hmac
import os
import requests
from pathlib import Path
from functools import lru_cache
from requests.auth import HTTPBasicAuth
import razorpay
from dotenv import load_dotenv

_ENV_PATH=Path(__file__).resolve().parent/".env"
load_dotenv(_ENV_PATH)

# Client initialization (singleton via lru_cache)
@lru_cache(maxsize=1)
def init_razorpay_client()-> razorpay.Client:

    """
    Load Razorpay API credentials from .env and return a configured client.
    The client is instantiated once and cached for the lifetime of the process.
    Raises EnvironmentError if either key is missing.
    Returns:
        razorpay.Client ready to call payment-link and order APIs.
    """

    key_id=os.getenv("RAZORPAY_KEY_ID","").strip()
    key_secret=os.getenv("RAZORPAY_KEY_SECRET","").strip()

    if not key_id or not key_secret:
        raise EnvironmentError(
            "RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET must be set in chat_agent/.env"
        )

    client=razorpay.Client(auth=(key_id,key_secret))
    client.set_app_details({"title": "FlowCart", "version": "0.1.0"})

    return client

# Create payment link

def create_payment_link(
        amount_inr: float,
        description: str,
        customer_name: str,
        customer_email: str,
        customer_phone: str,
        order_number: str,
        callback_url: str = None,
) -> dict:
    """
    Create a Razorpay Payment Link in test mode and return the link details.
    Args:
        amount_inr:      Order grand total in Indian Rupees (e.g. 1849.00).
        description:     Short description shown on the payment page.
        customer_name:   Full name of the customer.
        customer_email:  Customer's email address for receipt.
        customer_phone:  Customer's phone number (E.164, e.g. "+919876543210").
        order_number:    Internal order reference (e.g. "ORD-20260829-A1B2C3").
        callback_url:    Razorpay will POST the payment result here after pay.
    Returns:
        dict with keys:
            success (bool)       — True if link was created without error
            payment_link_id      — Razorpay's internal link ID
            short_url            — The URL to send to the customer
            amount_inr           — Original amount passed in
            amount_paise         — Amount in paise sent to Razorpay
            order_number         — Echo of the order_number argument
            error (str)          — Present only when success=False
    """

    import time

    if not callback_url:
        callback_url = os.getenv("RAZORPAY_CALLBACK_URL", "http://localhost:8000/webhook/razorpay").strip()

    client = init_razorpay_client()
    amount_paise = int(round(amount_inr * 100))

    payload = {
        "amount":      amount_paise,
        "currency":    "INR",
        "description": description,
        "customer": {
            "name":    customer_name,
            "email":   customer_email,
            "contact": customer_phone,
        },
        "notify": {
            "sms":   True,
            "email": True,
        },
        "reminder_enable": True,
        "callback_url": callback_url,
        "notes": {
            "order_number": order_number,
        },
    }

    last_error = ""
    for attempt in range(2):          # 1 try + 1 retry on rate-limit
        try:
            response = client.payment_link.create(payload)  # type: ignore[attr-defined]
            return {
                "success":          True,
                "payment_link_id":  response["id"],
                "short_url":        response["short_url"],
                "amount_inr":       amount_inr,
                "amount_paise":     amount_paise,
                "order_number":     order_number,
            }
        except Exception as e:
            last_error = str(e)
            # Razorpay test-mode rate limit — wait and retry once
            if "too many requests" in last_error.lower() and attempt == 0:
                time.sleep(4)
                continue
            break   # non-rate-limit error → don't retry

    return {
        "success":      False,
        "error":        last_error,
        "order_number": order_number,
    }

# verify webhook signature 
def execute_mandate_charge(
    amount_inr: float,
    order_number: str,
    customer_id: str,
    token_id: str,
    email: str,
    phone: str,
) -> dict:
    """
    Phase 2 mandate auto-debit:

    Step A — Creates a REAL Razorpay Order via the Orders API.
              This order will appear in the Razorpay dashboard.

    Step B — Attempts a server-side recurring charge via
              POST /v1/payments/create/recurring using the stored token.
              In test mode with pre-seeded token IDs this will fail gracefully;
              the real Razorpay Order from Step A is still returned so it is
              visible in the dashboard and provable during a demo.

    Args:
        amount_inr:   Cart grand total in INR (e.g. 1799.00).
        order_number: Internal FlowCart order reference (e.g. "ORD-20260905-AB12CD").
        customer_id:  Razorpay customer ID stored on the mandate.
        token_id:     Razorpay token ID stored on the mandate.
        email:        Customer email (required by Razorpay recurring API).
        phone:        Customer phone in E.164 format.

    Returns a dict:
        success (bool)              — True even when Step B fails (Step A succeeded)
        razorpay_order_id (str)     — Real Razorpay order ID (always present on success)
        payment_id (str | None)     — Real Razorpay payment ID if Step B succeeded, else None
        api_charge_attempted (bool) — Whether the recurring charge endpoint was called
        api_charge_succeeded (bool) — Whether it returned a payment object
        error (str)                 — Present only when Step A itself fails
    """
    key_id     = os.getenv("RAZORPAY_KEY_ID", "").strip()
    key_secret = os.getenv("RAZORPAY_KEY_SECRET", "").strip()
    client     = init_razorpay_client()
    amount_paise = int(round(amount_inr * 100))

    # ── Step A: Create a real Razorpay Order ────────────────────────────────
    try:
        rzp_order = client.order.create({   # type: ignore[attr-defined]
            "amount":          amount_paise,
            "currency":        "INR",
            "receipt":         order_number,
            "payment_capture": 1,
            "notes": {
                "order_number": order_number,
                "payment_type": "mandate_auto_debit",
                "customer_id":  customer_id,
            },
        })
        razorpay_order_id = rzp_order["id"]
    except Exception as exc:
        # If order creation itself fails, surface the error — nothing else can proceed.
        return {
            "success":              False,
            "razorpay_order_id":    None,
            "payment_id":           None,
            "api_charge_attempted": False,
            "api_charge_succeeded": False,
            "error":                f"Razorpay order creation failed: {exc}",
        }

    # ── Step B: Attempt recurring charge against the mandate token ───────────
    payment_id           = None
    api_charge_succeeded = False
    try:
        resp = requests.post(
            "https://api.razorpay.com/v1/payments/create/recurring",
            json={
                "email":       email,
                "contact":     phone,
                "amount":      amount_paise,
                "currency":    "INR",
                "order_id":    razorpay_order_id,
                "customer_id": customer_id,
                "token":       token_id,
                "description": f"FlowCart Auto-Pay: {order_number}",
                "recurring":   1,
            },
            auth=HTTPBasicAuth(key_id, key_secret),
            timeout=10,
        )
        data = resp.json()
        if resp.status_code == 200:
            payment_id           = data.get("razorpay_payment_id") or data.get("id")
            api_charge_succeeded = bool(payment_id)
    except Exception:
        # Network timeout or unexpected error — Step A succeeded so we continue.
        pass

    # Return success regardless of Step B — Step A is what we can demo.
    return {
        "success":              True,
        "razorpay_order_id":    razorpay_order_id,
        "payment_id":           payment_id,          # None → user_service generates UUID
        "api_charge_attempted": True,
        "api_charge_succeeded": api_charge_succeeded,
    }


# verify webhook signature 
def verify_webhook_signature(
    payload_body: bytes,
    signature: str,
    secret: str | None = None,
) -> bool:
    """
    Verify the HMAC-SHA256 signature on an incoming Razorpay webhook request.
    Uses the Razorpay SDK's built-in utility when a client is available,
    falling back to a direct HMAC-SHA256 comparison otherwise.
    Razorpay signs every webhook POST body with:
        HMAC-SHA256(payload_body, RAZORPAY_WEBHOOK_SECRET)
    The resulting hex digest is sent in the X-Razorpay-Signature header.
    Args:
        payload_body: The raw bytes of the POST request body.
        signature:    The value of the X-Razorpay-Signature header.
        secret:       The webhook secret from the Razorpay dashboard.
                      Defaults to the RAZORPAY_WEBHOOK_SECRET env variable.
    Returns:
        True  — signature is valid, payload is authentic.
        False — signature mismatch or secret missing; reject the request.
    """

    if secret is None:
        secret=os.getenv("RAZORPAY_WEBHOOK_SECRET","").strip()

    if not secret:
        # cannot verify without secret
        return False 

    try:
        client=init_razorpay_client()
        client.utility.verify_webhook_signature( #type:ignore
        payload_body.decode("utf-8"),
        signature,
        secret,
        )

        return True

    except Exception:
        pass

    # Fallback: manual HMAC-SHA256
    expected=hmac.new(
        secret.encode("utf-8"),
        payload_body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected,signature)

