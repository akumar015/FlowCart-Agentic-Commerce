"""
chat_agent/agent_graph.py

Graph topology:
    agent ──safe tools──► tools ──► agent
    agent ──checkout────► payment_gate
                              ├── ✅ ──► payment_tools ──► agent
                              └── ❌ ──► agent (rejection injected)
"""

import json
import sys
import uuid
from pathlib import Path
from typing import Annotated, Literal
import os 

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
load_dotenv(Path(__file__).resolve().parent / ".env")


import databases.inventory_service as inventory_service
import databases.user_service as user_service
from chat_agent.razorpay_client import create_payment_link, execute_mandate_charge
from chat_agent.agent_tools import (
    search_catalog,
    get_product_info,
    check_stock_availability,
    add_to_cart,
    view_cart,
    remove_from_cart,
    clear_cart,
    get_delivery_address,
    get_order_history,
    initiate_checkout,
)

class AgentState(TypedDict):
    messages:Annotated[list, add_messages]  # full conversation history
    user_id: int                            # logged-in user
    session_id: str                            # cart + audit key
    payment_status: str                            
    # "none" |   "link_sent" | "paid" | "failed"


SYSTEM_PROMPT = """You are FlowCart, a high-IQ conversational shopping assistant and technical commerce advisor.
You help users discover products, compare technical specifications, manage carts, and checkout seamlessly.

## Your Core Capabilities
1. **Intelligent Technical Recommender**:
   When users ask for recommendations, comparisons, or products matching specific criteria (e.g., "phone with big battery under 40k", "gaming laptop under 80k with good GPU", "ANC earbuds", "marathon running shoes"):
   - Call `search_catalog` using smart parameters (use category, max_price, and short focused keywords like "phone", "gaming", "battery", "RTX", "ANC", "running" — NEVER pass entire long questions as the query string).
   - Carefully inspect the technical specifications in product descriptions (Battery mAh, CPU/GPU, TGP wattage, RAM, display, charging speed, shoe midsole/plate, fabric).
   - Rank the top 3 to 5 options based on their specs and relevance.
   - Present a clear comparison table or structured ranked list showing:
     * **Rank & Product Name** (with formatted price, e.g. ₹39,999)
     * **Key Relevant Specs** (e.g. "5,500 mAh battery, 100W SuperVOOC")
     * **Score / Rating** (e.g. "Battery Score: 9.4/10" or "Performance: 9.2/10")
     * **Why Recommended** (a 1-sentence technical justification)

2. **Cart & Conversational Checkout**:
   - Help users add variants (color, size/storage) to their cart.
   - Maintain the cart (view, remove, clear).
   - Before checkout:
     a. Always call `view_cart` to summarize items and grand total.
     b. Always call `get_delivery_address` to confirm shipping destination.
     c. Ask for explicit confirmation ("Shall I proceed with checkout?") and wait for the user's "yes".

3. **Proactive Upsell & Cross-Sell (IMPORTANT)**:
   Immediately after a successful `add_to_cart`, you MUST suggest 2 complementary accessories by doing the following:
   a. Look at what was just added. Identify the category and key use-case.
   b. Call `search_catalog` ONCE with a short keyword and matching category to find accessories:
      - Smartphone added → search "charger earbuds" in "Electronics & Gadgets" (max_price=10000)
      - Gaming Laptop added → search "mouse keyboard SSD" in "Electronics & Gadgets" (max_price=15000)
      - Running Shoes added → search "dry fit running" in "Clothing" (max_price=3000)
      - Clothing/Apparel added → search "running shoes" in "Footwear" (max_price=15000)
      - Earbuds/Headphones added → no upsell needed, skip.
   c. Pick the top 2 most relevant results from the search.
   d. Write your cart-confirmation message naturally, then append EXACTLY this block at the very end:

   __UPSELL__{"items":[{"product_id":X,"variant_id":Y,"title":"Product Name","price":ZZZZ,"reason":"One-line why this pairs well"},...]}__UPSELL__

   - `variant_id` MUST be a real variant ID from the search results (use the first variant's id).
   - `price` MUST be the numeric variant price (no currency symbol).
   - Include EXACTLY 2 items in the array. No more, no less.
   - If search returns fewer than 2 results, include only what is available.
   - If NOTHING relevant is found, omit the __UPSELL__ block entirely.

## Rules You Must NEVER Break
1. NEVER fabricate product names, prices, variant IDs, or stock info. Always call `search_catalog` or `get_product_info`.
2. Keep search queries short and clean: use `category`, `max_price`, `min_price` filters whenever applicable. If a specific keyword returns 0 results, retry with a broader query or browse the category.
3. NEVER call `initiate_checkout` speculatively. Only call it when the user explicitly agrees to place the order.
4. ALWAYS pass the correct `session_id` and `user_id` provided in the session context.
5. Format prices as ₹X,XXX (e.g. ₹39,999).
6. The __UPSELL__ block must be valid JSON. Never break the format.

## Tone & Style
- Professional, knowledgeable, and concise.
- Act like an expert product specialist who genuinely understands hardware and specs.
- On spend limit or category blocks: explain the situation transparently and present the manual payment link.
- On out-of-stock: proactively suggest the closest alternative.
"""


# Tool Lists

SAFE_TOOLS = [
    search_catalog,
    get_product_info,
    check_stock_availability,
    add_to_cart,
    view_cart,
    remove_from_cart,
    clear_cart,
    get_delivery_address,
    get_order_history,
    initiate_checkout,   # LLM can call it; graph intercepts it at the gate
]
ALL_TOOLS_BY_NAME = {t.name: t for t in SAFE_TOOLS}


# node 1: agent node
def build_agent_node(llm_with_tools):
    """Returns a closure that calls the LLM and returns updated state."""

    def agent_node(state: AgentState) -> dict:
    # Prepend the system prompt with session context with every call
        session_context = (
            f"\n\n[Session Info]\n"
            f"user_id={state['user_id']}  "
            f"session_id={state['session_id']}  "
            f"payment_status={state['payment_status']}"
    )

        system_msg = SystemMessage(content=SYSTEM_PROMPT + session_context)

        response=llm_with_tools.invoke([system_msg]+state['messages'])
        return {"messages": [response]}

    return agent_node

# node 2: tool node
tool_node=ToolNode(SAFE_TOOLS)

# node 3: payment gate node
def payment_gate_node(state: AgentState) -> dict:
    """
    Intercepts initiate_checkout tool calls and decides the payment path.

    Routing priority:
      1. Mandate auto-debit  — verify_mandate_for_payment() passes all 3 guardrails
      2. Payment link        — mandate fails but spend_limit check passes (fallback)
      3. Blocked             — spend limit exceeded; rejection synthesised here

    The ToolMessage returned on the approved paths carries a `payment_method`
    key that payment_tools_node reads to choose the right execution path.
    """
    session_id = state["session_id"]
    user_id    = state["user_id"]

    # Find the initiate_checkout tool_call_id from the last AI message
    last_ai_message = state["messages"][-1]
    checkout_call = next(
        (tc for tc in last_ai_message.tool_calls if tc["name"] == "initiate_checkout"),
        None,
    )
    tool_call_id = checkout_call["id"] if checkout_call else "unknown"

    # Fetch cart once — shared by both checks
    cart        = inventory_service.cart_get(session_id)
    grand_total = float(cart.get("grand_total", 0.0))
    item_count  = int(cart.get("total_items_count", 0))

    # ── Priority 1: Mandate guardrail check ─────────────────────────────────
    mandate_check = user_service.verify_mandate_for_payment(user_id, cart)

    if mandate_check.get("allowed"):
        mandate = mandate_check["mandate"]
        reason  = mandate_check["reason"]

        user_service.log_agent_audit(
            session_id=session_id,
            action_type="PAYMENT_GATE_CHECK",
            reasoning=reason,
            payload={
                "cart_total":     grand_total,
                "item_count":     item_count,
                "allowed":        True,
                "payment_method": "mandate_auto_debit",
                "mandate_type":   mandate.get("mandate_type"),
                "mandate_id":     mandate.get("id"),
            },
            user_id=user_id,
            is_gated=True,
            user_confirmed=True,
        )

        gate_msg = ToolMessage(
            content=json.dumps({
                "gate":           "approved",
                "payment_method": "mandate_auto_debit",
                "grand_total":    grand_total,
                "reason":         reason,
                "mandate": {
                    "id":                   mandate["id"],
                    "mandate_type":         mandate["mandate_type"],
                    "mandate_token":        mandate["mandate_token"],
                    "razorpay_customer_id": mandate.get("razorpay_customer_id"),
                    "razorpay_token_id":    mandate.get("razorpay_token_id"),
                    "max_amount_per_tx":    mandate["max_amount_per_tx"],
                    "allowed_categories":   mandate.get("allowed_categories", []),
                },
            }),
            tool_call_id=tool_call_id,
            name="initiate_checkout",
        )
        return {"messages": [gate_msg]}

    # ── Priority 2: Fallback — standard spend limit check ───────────────────
    # Mandate failed (no mandate, over limit, or bad category) — try payment link path.
    fallback_reason = mandate_check.get("reason", "")
    check   = user_service.verify_agent_spend_permission(user_id, grand_total)
    allowed = check.get("allowed", False)
    reason  = check.get("reason", "")

    user_service.log_agent_audit(
        session_id=session_id,
        action_type="PAYMENT_GATE_CHECK",
        reasoning=f"Mandate path unavailable ({fallback_reason}). Spend-limit check: {reason}",
        payload={
            "cart_total":        grand_total,
            "item_count":        item_count,
            "allowed":           allowed,
            "spend_limit":       check.get("spend_limit"),
            "mandate_blocked_reason": fallback_reason,
            "payment_method":    "link" if allowed else "blocked",
        },
        user_id=user_id,
        is_gated=True,
        user_confirmed=allowed,
    )

    if allowed:
        gate_msg = ToolMessage(
            content=json.dumps({
                "gate":           "approved",
                "payment_method": "link",
                "grand_total":    grand_total,
                "reason":         reason,
                "mandate_note":   fallback_reason,
            }),
            tool_call_id=tool_call_id,
            name="initiate_checkout",
        )
        return {"messages": [gate_msg]}

    # ── Priority 3: Blocked — spend limit exceeded ───────────────────────────
    spend_limit = float(check.get("spend_limit", 0.0) or 0.0)

    gate_msg = ToolMessage(
        content=json.dumps({
            "gate":        "blocked",
            "reason":      reason,
            "grand_total": grand_total,
            "spend_limit": spend_limit,
        }),
        tool_call_id=tool_call_id,
        name="initiate_checkout",
    )

    rejection_msg = AIMessage(content=(
        f"I can't proceed with checkout right now.\n\n"
        f"Your cart total of **₹{grand_total:,.2f}** exceeds your "
        f"per-transaction agent spend limit of **₹{spend_limit:,.2f}**.\n\n"
        f"Here's what you can do:\n"
        f"- Remove some items from your cart to bring the total under the limit, or\n"
        f"- Contact support to request a higher spend limit.\n\n"
        f"Would you like me to show what's in your cart so you can decide what to remove?"
    ))
    return {"messages": [gate_msg, rejection_msg]}

# node 4: payment tools node
def payment_tools_node(state: AgentState) -> dict:
    """
    Runs only after payment_gate approves.

    Dual-path execution based on payment_method from the gate ToolMessage:

    PATH A — mandate_auto_debit:
        1. Fetch user + cart + address.
        2. Create internal order record.
        3. Call execute_mandate_charge() → creates real Razorpay Order + attempts recurring charge.
        4. Call execute_mandate_payment() → records debit in DB + audit log.
        5. Clear cart. Return zero-click success AIMessage.

    PATH B — link (fallback):
        1–2. Same as above.
        3. Call create_payment_link() → returns Razorpay payment URL.
        4. Bind link to order. Return AIMessage with the URL.
    """
    session_id = state["session_id"]
    user_id    = state["user_id"]

    # Parse gate ToolMessage to get payment_method
    gate_msg_content = state["messages"][-1].content
    try:
        gate_data = json.loads(gate_msg_content if isinstance(gate_msg_content, str)
                               else json.dumps(gate_msg_content))
    except (json.JSONDecodeError, TypeError):
        gate_data = {}

    payment_method = gate_data.get("payment_method", "link")

    # ── Common setup ─────────────────────────────────────────────────────────
    user    = user_service.get_user_by_id(user_id) or {}
    cart    = inventory_service.cart_get(session_id)
    address = user_service.get_user_default_address(user_id) or {}

    grand_total: float = float(cart.get("grand_total") or 0.0)

    phone = user.get("phone", "+910000000000")
    if not phone.startswith("+"):
        phone = "+91" + phone.lstrip("0")

    # Create the internal order record (same for both paths)
    order = user_service.create_order_from_cart(
        session_id=session_id,
        user_id=user_id,
        cart_data=cart,
        shipping_address_id=address.get("id"),
    )

    if not order.get("success"):
        error_msg = order.get("error", "Failed to create order.")
        return {
            "messages":       [AIMessage(content=f"Couldn't create your order: {error_msg}")],
            "payment_status": "failed",
        }

    order_id     = int(order["order_id"])
    order_number = str(order.get("order_number", f"ORD-{uuid.uuid4().hex[:8].upper()}"))

    # ── PATH A: Mandate Auto-Debit ────────────────────────────────────────────
    if payment_method == "mandate_auto_debit":
        mandate = gate_data.get("mandate", {})

        # Step A+B: Create real Razorpay Order + attempt recurring charge
        charge = execute_mandate_charge(
            amount_inr=grand_total,
            order_number=order_number,
            customer_id=mandate.get("razorpay_customer_id", ""),
            token_id=mandate.get("razorpay_token_id", ""),
            email=user.get("email", ""),
            phone=phone,
        )

        if not charge.get("success"):
            # Razorpay Order creation itself failed — fall through to link
            user_service.log_agent_audit(
                session_id=session_id,
                action_type="MANDATE_CHARGE_FAILED",
                reasoning=charge.get("error", "Razorpay order creation failed."),
                payload={"order_id": order_id, "order_number": order_number},
                user_id=user_id,
                is_gated=True,
                user_confirmed=False,
            )
            payment_method = "link"   # fall through below

        else:
            # Record the debit in DB (Phase 1 function) and clear cart
            user_service.execute_mandate_payment(
                user_id=user_id,
                order_id=order_id,
                amount=grand_total,
                mandate_id=mandate.get("id"),
                session_id=session_id,
                razorpay_order_id=charge.get("razorpay_order_id"),
                real_payment_id=charge.get("payment_id"),   # None → fn generates UUID
            )
            inventory_service.cart_clear(session_id)

            masked_token = mandate.get("mandate_token", "")[-4:] or "????"
            rzp_order_id = charge.get("razorpay_order_id", "N/A")
            api_ok       = charge.get("api_charge_succeeded", False)

            reply = AIMessage(content=(
                f"✅ **Payment Complete — No action needed!**\n\n"
                f"**Order:** {order_number}\n"
                f"**Amount:** ₹{grand_total:,.2f}\n"
                f"**Paid via:** Pre-authorized {mandate.get('mandate_type', 'UPI_AUTOPAY')} "
                f"mandate (···{masked_token})\n"
                f"**Razorpay Order:** `{rzp_order_id}`\n"
                f"**Delivering to:** {address.get('street_address', '')}, "
                f"{address.get('city', '')}\n\n"
                + (
                    "_Your UPI Autopay mandate was charged automatically._"
                    if api_ok else
                    "_Mandate charge recorded. In production, your UPI Autopay mandate "
                    "would be debited automatically at this step._"
                )
            ))
            return {"messages": [reply], "payment_status": "paid"}

    # ── PATH B: Razorpay Payment Link (original flow, unchanged) ─────────────
    link_result = create_payment_link(
        amount_inr=grand_total,
        description=f"FlowCart Order {order_number}",
        customer_name=user.get("name", "Customer"),
        customer_email=user.get("email", ""),
        customer_phone=phone,
        order_number=order_number,
    )

    if link_result.get("success"):
        payment_link_id = link_result["payment_link_id"]
        short_url       = link_result["short_url"]

        user_service.link_razorpay_payment(
            order_id=order_id,
            payment_link_id=payment_link_id,
            razorpay_order_id=None,
        )

        reply = AIMessage(content=(
            f"Your order **{order_number}** is confirmed!\n\n"
            f"**Order Total:** ₹{grand_total:,.2f}\n"
            f"**Delivering to:** {address.get('street_address', '')}, "
            f"{address.get('city', '')}\n\n"
            f"**Complete your payment here:**\n{short_url}\n\n"
            f"The link is valid for 24 hours. "
            f"You'll get a confirmation SMS and email once paid."
        ))

    else:
        error = link_result.get("error", "unknown error")

        user_service.log_agent_audit(
            session_id=session_id,
            action_type="PAYMENT_LINK_FAILED",
            reasoning=f"Razorpay link creation failed: {error}",
            payload={"order_number": order_number, "error": error},
            user_id=user_id,
            is_gated=True,
            user_confirmed=False,
        )

        reply = AIMessage(content=(
            f"⚠️ I created your order **{order_number}**, but hit a snag generating "
            f"the payment link: _{error}_\n\n"
            f"Please try again or contact support."
        ))

    return {
        "messages":       [reply],
        "payment_status": "link_sent" if link_result.get("success") else "failed",
    }



# Routing Functions 
def should_continue(state: AgentState) -> Literal["tools", "payment_gate", "__end__"]:
    """
    Routes the output of the agent node.
      - No tool calls         → END (agent replied directly to user)
      - initiate_checkout     → payment_gate
      - Any other tool calls  → tools
    """
    last_msg = state["messages"][-1]
    # No tool calls → done, return to user
    if not hasattr(last_msg, "tool_calls") or not last_msg.tool_calls:
        return "__end__"
    # Check if any tool call is initiate_checkout
    for tc in last_msg.tool_calls:
        if tc["name"] == "initiate_checkout":
            return "payment_gate"
    # All other tool calls go to the safe tool node
    return "tools"


def gate_decision(state: AgentState) -> Literal["payment_tools", "__end__"]:
    """
    Routes the output of payment_gate_node.
    - gate=approved  → last msg is ToolMessage  → payment_tools
    - gate=blocked   → last msg is AIMessage    → __end__  (response already synthesised)
    """
    last_msg = state["messages"][-1]

    # Approved path: gate returned a single ToolMessage with gate=approved
    if isinstance(last_msg, ToolMessage):
        try:
            content = last_msg.content
            if isinstance(content, list):
                content = json.dumps(content)
            data = json.loads(content)
            if data.get("gate") == "approved":
                return "payment_tools"
        except (json.JSONDecodeError, AttributeError):
            pass

    # Blocked path: payment_gate_node already returned [ToolMessage, AIMessage].
    # The rejection AIMessage is now the last message — go straight to END.
    return "__end__"



#----------------------------------------------------------------
# Graph Assembly

def build_graph():
    """
    Builds and compiles the LangGraph state machine.
    Call once and cache (use @st.cache_resource in app.py).
    Returns:
        A compiled LangGraph graph ready to invoke.
    """

    # llm setup
    llm=ChatOpenAI(
        model='gpt-4o-mini',
        base_url = "https://openrouter.ai/api/v1",
        api_key = os.getenv("OPENROUTER_API_KEY"), # type:ignore
        temperature=0.2
    )
    llm_with_tools=llm.bind_tools(SAFE_TOOLS)

    # node instances
    agent_node=build_agent_node(llm_with_tools)

    # graph definition 
    graph=StateGraph(AgentState)

    graph.add_node("agent",agent_node)
    graph.add_node("tools", tool_node)
    graph.add_node("payment_gate", payment_gate_node)
    graph.add_node("payment_tools", payment_tools_node)

    # entry point 
    graph.set_entry_point("agent")

    # edges
    graph.add_conditional_edges(
        'agent',
        should_continue,
        {
            "__end__": END,
            "tools": "tools",
            "payment_gate": "payment_gate",
        }
    )

    graph.add_edge("tools","agent")

    graph.add_conditional_edges(
        "payment_gate",
        gate_decision,
        {
            "payment_tools": "payment_tools",
            "__end__": END,          # blocked path — rejection already synthesised
        }
    )

    # payment_tools already returns a complete AIMessage response.
    # Routing back to agent would trigger Gemini's "model prefilling" error
    # (LLM called with AIMessage as the last message). Go straight to END.
    graph.add_edge("payment_tools", END)

    # memory (per thread checkpoint)
    memory=MemorySaver()
    compiled=graph.compile(checkpointer=memory)

    return compiled


# ============================================================================
# Smoke Test
# ============================================================================

if __name__ == "__main__":
    import os
    from langchain_core.messages import HumanMessage
    from langchain_core.runnables import RunnableConfig

    def _text(msg) -> str:
        """Extract plain text from an AIMessage regardless of content shape.
        Gemini returns list[dict] with 'type'/'text' keys; plain models return str.
        """
        c = msg.content
        if isinstance(c, str):
            return c
        # structured content blocks → join all text parts
        return "".join(
            part["text"] for part in c
            if isinstance(part, dict) and part.get("type") == "text"
        )

    print("Building graph...")
    graph = build_graph()
    print("Graph compiled ✅\n")

    # Use test user_id=1 and a fixed session
    TEST_USER_ID  = 1
    TEST_SESSION  = "smoke-test-session"
    THREAD_CONFIG: RunnableConfig = {"configurable": {"thread_id": TEST_SESSION}}

    # --- Turn 1: Greeting ---------------------------------------------------
    print("--- Turn 1: Greeting ---")
    result = graph.invoke(
        {
            "messages":       [HumanMessage(content="Hi!")],
            "user_id":        TEST_USER_ID,
            "session_id":     TEST_SESSION,
            "payment_status": "none",
        },
        config=THREAD_CONFIG,
    )
    print("Agent:", _text(result["messages"][-1]))

    # --- Turn 2: Product search ---------------------------------------------
    print("\n--- Turn 2: Product search ---")
    result = graph.invoke(
        {
            "messages":       [HumanMessage(content="Show me whey protein under ₹2000")],
            "user_id":        TEST_USER_ID,
            "session_id":     TEST_SESSION,
            "payment_status": "none",
        },
        config=THREAD_CONFIG,
    )
    print("Agent:", _text(result["messages"][-1]))

    # --- Turn 3: View cart (should be empty) --------------------------------
    print("\n--- Turn 3: View cart ---")
    result = graph.invoke(
        {
            "messages":       [HumanMessage(content="What's in my cart?")],
            "user_id":        TEST_USER_ID,
            "session_id":     TEST_SESSION,
            "payment_status": "none",
        },
        config=THREAD_CONFIG,
    )
    print("Agent:", _text(result["messages"][-1]))




