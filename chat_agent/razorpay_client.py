"""
chat_agent/razorpay_client.py

Exposes three functions used by the payment_tools node in agent_graph.py:
  init_razorpay_client()       → razorpay.Client (cached singleton)
  create_payment_link(...)     → dict  with short_url, payment_link_id
  verify_webhook_signature(...) → bool
"""

import hashlib
import hmac
import os
from pathlib import Path
from functools import lru_cache
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
        callback_url: str="http://localhost:8000/webhook/razorpay"
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

    client=init_razorpay_client()

    # convert amount to smallest currency unit (razorpay works only in smallest currency unit)

    amount_paise=int(round(amount_inr*100))

    payload={
        'amount': amount_paise,
        'currency': 'INR',
        'description': description,
        'customer':{
            'name': customer_name,
            'email': customer_email,
            'contact': customer_phone
        },
        'notify':{
            'sms': True,
            'email': True
        },
        'remainder_enable': True,
        'callback_url': callback_url,
        'callback_method': "get",
        'notes':{
            'order_number': order_number,
        },
    }

    try: 
        response=client.payment_link.create(payload) #type: ignore[attr-defined]
        return{
            'success': True,
            'payment_link_id': response['id'],
            'short_url': response['short_url'],
            'amount_inr': amount_inr,
            'amount_paise': amount_paise,
            'order_number': order_number,
        }

    except Exception as e:
        return{
            'success': False,
            'error': str(e),
            'order_number': order_number
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

