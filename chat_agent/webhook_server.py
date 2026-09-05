"""
FastAPI webhook server that listens for Razorpay payment callbacks and closes the checkout loop started by agent_graph.py.
Endpoints:
  POST /webhook/razorpay          — Razorpay payment event callback
  GET  /webhook/status/{order_id} — Frontend polls for payment status
  GET  /health                    — Readiness check
Startup:
  uvicorn chat_agent.webhook_server:app --host 0.0.0.0 --port 8000
"""

#libraries
import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

from databases import user_service, inventory_service
from chat_agent.razorpay_client import verify_webhook_signature


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(_ENV_PATH)

WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET", "").strip()


# FastAPI App
app=FastAPI(
    title="FlowCart Webhook Server",
    description="Razorpay payment callback handler for conversational checkout agent",
    version="1.0.0"
)

# Health check
@app.get("/health")
async def health():
    """Readiness check- returns 200 if the server is up"""
    return{
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "webhook_server_configured": bool(WEBHOOK_SECRET),
    }

# Payment status polling
@app.get("/webhook/status/{order_id}")
async def get_payment_status(order_id: int):
    """
    Frontend polls this to check if a payment has been confirmed.

    Returns:
        order_id, order_number, payment_status, order_status
    """

    conn= user_service.get_user_db()
    cursor=conn.cursor()
    cursor.execute(
        """
        SELECT id, order_number, payment_status, order_status,
               razorpay_payment_id, updated_at
        FROM orders
        WHERE id = ?
        """,
        (order_id,),
    )

    row = cursor.fetchone()
    conn.close()

    if not row:
        return HTTPException(status_code=404, detail=f"Order {order_id} not found")

    return dict(row)

# Razorpay webhook handler
@app.post("/webhook/razorpay")
async def handle_razerpay_webhook(request: Request):
    """
    Receives Razorpay payment event POSTs.
    Security:
        - Verifies X-Razorpay-Signature before touching the database.
        - If signature is missing or invalid → HTTP 400 (silent fail to attacker).
    Handled events:
        payment_link.paid       → finalize order, clear cart, log audit
        payment_link.expired    → mark order failed, log audit
        payment_link.cancelled  → mark order failed, log audit
    """

    # 1. read raw row body before parsing JSON (signature is over raw bytes)
    body=await request.body()

    # 2. ssignature verification
    signature=request.headers.get("X-Razorpay-Signature","")

    if not signature:
        raise HTTPException(status_code=400, detail="Missing X-Razorpay-Signature header")
    is_valid = verify_webhook_signature(body, signature, WEBHOOK_SECRET)
    if not is_valid:
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    # 3. Parse payload
    try: 
        payload=json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    event=payload.get("event","")
    entity=payload.get("payload", {}).get("payment_link",{}).get("entity",{})
    payment=payload.get("payload", {}).get("payment",{}).get("entity",{})

    print(f"Razorpay event recieved: {event}")

    # 4. Extract order details from razorpay notes
    order_number=entity.get("notes",{}).get("order_number","")
    payment_link_id=entity.get("id","")
    razorpay_payment_id=payment.get("id","")
    razorpay_signature=signature

    # 5. look up internal order by payment_link_id
    order=_get_order_by_payment_link_id(payment_link_id)

    # Event: Payment successful 
    if event == "payment_link.paid":
        if order:
            order_id=order["id"]
            session_id=order["session_id"]
            user_id=order["user_id"]

            # mark order as paid in DB
            user_service.finalize_order_payment(
                order_id=order_id,
                payment_id=razorpay_payment_id,
                signature=razorpay_signature,
                status='paid',
            )

            # clear cart, clean the session 
            inventory_service.cart_clear(session_id)

            # log to audit trail
            user_service.log_agent_audit(
                session_id=session_id,
                action_type="PAYMENT_CONFIRMED",
                reasoning=f"Razorpay confirmed payment for order {order_number}",
                payload={
                    "event": event,
                    "order_id": order_id,
                    "order_number": order_number,
                    "payment_link_id": payment_link_id,
                    "razorpay_payment_id": razorpay_payment_id,
                    "amount": entity.get("amount", 0) / 100,  # paise → INR
                },
                user_id=user_id,
                is_gated=True,
                user_confirmed=True
            )

            print(f"payment_link.paid received but no order found for link_id={payment_link_id}")

            
    # Event: Payment link expired 
    elif event == "payment_link.expired":
        if order:
            _mark_order_failed(order, event, order_number, payment_link_id)
        else:
            print(f"payment_link.expired — no order found for link_id={payment_link_id}")


    # Event: Payment link cancelled 
    elif event == "payment_link.cancelled":
        if order:
            _mark_order_failed(order, event, order_number, payment_link_id)
        else:
            print(f"payment_link.cancelled — no order found for link_id={payment_link_id}")


    # Unhandled events: acknowledge but ignore 
    else:
        print(f"ℹ️  Unhandled event type: {event} — acknowledged and ignored")
    # Razorpay expects a 200 OK response, always
    return {"status": "ok"}



#--------------------------------------------------------------
# Internal helpers 
def _get_order_by_payment_link_id(payment_link_id: str) -> dict | None:
    """Look up an order row using the Razorpay payment link ID."""
    if not payment_link_id:
        return None
    conn = user_service.get_user_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM orders WHERE razorpay_payment_link_id = ? LIMIT 1",
        (payment_link_id,),
    )
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None
def _mark_order_failed(order: dict, event: str, order_number: str, payment_link_id: str):
    """Shared logic for expired and cancelled payment link events."""
    order_id = order["id"]
    session_id = order["session_id"]
    user_id = order["user_id"]
    conn = user_service.get_user_db()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE orders
        SET payment_status = 'failed',
            order_status   = 'cancelled',
            updated_at     = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (order_id,),
    )
    conn.commit()
    conn.close()
    user_service.log_agent_audit(
        session_id=session_id,
        action_type="PAYMENT_FAILED",
        reasoning=f"Razorpay event '{event}' for order {order_number}",
        payload={
            "event": event,
            "order_id": order_id,
            "order_number": order_number,
            "payment_link_id": payment_link_id,
        },
        user_id=user_id,
        is_gated=True,
        user_confirmed=False,
    )
    print(f"Order {order_number} marked as FAILED (event={event})")