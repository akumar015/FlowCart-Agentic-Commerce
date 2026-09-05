import os
import sys
import uuid
import json
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional

# Add project root to sys path
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from databases import user_service, inventory_service
from chat_agent.agent_graph import build_graph
from langchain_core.messages import HumanMessage

app = FastAPI(title="FlowCart API")

graph = build_graph()

# Allow Vite frontend (any local port)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:5175",
        "http://127.0.0.1:5175",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    user_id: int
    session_id: str
    message: str
    payment_status: str = "none"

def _get_all_users():
    """Helper to fetch all users since user_service might not have it directly exposed if it's a raw query."""
    conn = user_service.get_user_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users")
    users = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return users

@app.get("/api/users")
def get_users():
    return {"users": _get_all_users()}

@app.get("/api/users/{user_id}")
def get_user_profile(user_id: int):
    profile = user_service.get_user_by_id(user_id)
    if not profile:
        raise HTTPException(status_code=404, detail="User not found")
    mandate = user_service.get_active_mandate(user_id)
    address = user_service.get_user_default_address(user_id)
    return {
        "profile": profile,
        "mandate": mandate,
        "address": address
    }

@app.get("/api/cart/{session_id}")
def get_cart(session_id: str):
    cart = inventory_service.cart_get(session_id)
    return {"cart": cart}

@app.get("/api/suggestions")
def get_suggestions():
    return {
        "suggestions": [
            "Show phones with 5000+ mAh battery",
            "Recommend a gaming laptop with RTX 4050",
            "Show ANC headphones with great battery life",
            "I need shoes for marathon running",
            "What is in my cart?",
            "Checkout my order"
        ]
    }

def _extract_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(part.get("text", "") for part in content if part.get("type") == "text")
    return str(content)

import re as _re

def _parse_upsell(reply_text: str):
    """
    Extracts __UPSELL__...content...(__UPSELL__)? from the agent reply.
    Handles two formats the model emits:
      - {"items": [...]}
      - [...]
    Closing tag is optional. Opening tag spelling is fuzzy.
    Returns (clean_text, upsell_items_list).
    """
    # Match __UPSEL*__ then grab everything until closing __UPSELL__ (optional)
    pattern = r"__UPSEL[A-Z_]*__\s*([\[{].*?)(?:__UPSELL__\s*|$)"
    match = _re.search(pattern, reply_text, _re.DOTALL)
    if not match:
        return reply_text, []

    raw = match.group(1).strip()
    # Strip the entire block from the visible reply (greedy to closing tag if present)
    clean_text = _re.sub(r"__UPSEL[A-Z_]*__.*?(?:__UPSELL__|$)", "", reply_text, flags=_re.DOTALL).strip()

    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return clean_text, data
        if isinstance(data, dict):
            return clean_text, data.get("items", [])
        return clean_text, []
    except (json.JSONDecodeError, AttributeError):
        return clean_text, []

@app.post("/api/chat")
def chat(req: ChatRequest):
    thread_config = {"configurable": {"thread_id": req.session_id}}
    
    try:
        result = graph.invoke(
            {
                "messages": [HumanMessage(content=req.message)],
                "user_id": req.user_id,
                "session_id": req.session_id,
                "payment_status": req.payment_status,
            },
            config=thread_config,
        )
        
        last_msg = result["messages"][-1]
        raw_reply = _extract_text(last_msg.content)
        reply_text, upsell_items = _parse_upsell(raw_reply)
        new_payment_status = result.get("payment_status", req.payment_status)
        
        # also get latest audit logs
        audit_logs = user_service.get_session_audit_trail(req.session_id)
        
        return {
            "reply": reply_text,
            "payment_status": new_payment_status,
            "audit_logs": audit_logs,
            "upsell_items": upsell_items,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
