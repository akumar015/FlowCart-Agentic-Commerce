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

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_google_genai import ChatGoogleGenerativeAI
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
from chat_agent.razorpay_client import create_payment_link
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


SYSTEM_PROMPT = """You are FlowCart, a friendly and efficient AI shopping assistant 
embedded inside a conversational checkout experience.
## Your Capabilities
You can search products, manage carts, look up user profiles and addresses,
check order history, and initiate secure checkouts — all via your tools.
## Rules You Must NEVER Break
1. NEVER fabricate product names, prices, variant IDs, or stock info.
   Always call search_catalog or get_product_info first.
2. NEVER call initiate_checkout speculatively.
   Only call it after the user has EXPLICITLY confirmed they want to pay.
3. ALWAYS pass the correct session_id and user_id to every tool you call.
   These are provided in the conversation context below.
4. Before checkout, always:
   a. Call view_cart to show the full order summary.
   b. Call get_delivery_address to confirm the shipping address.
   c. Ask the user "Shall I proceed to checkout?" and wait for a yes.
## Tone & Style
- Be concise and conversational. Avoid bullet-point walls.
- Format prices as ₹X,XXX (e.g. ₹1,849).
- On payment link: present it clearly with the total amount.
- On spend limit block: be empathetic, tell the limit, suggest removing items.
- On out-of-stock: offer to find alternatives immediately.
- On payment failure: offer to generate a fresh payment link.
## Session Context
Your session_id and user_id are injected into every message. Use them as-is.
Start the conversation by greeting the user by name using get_user_profile.
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
def payment_gate_node(state: AgentState)-> dict:
    """
    Intercepts initiate_checkout tool calls.
    1. Gets cart total.
    2. Verifies against user spend limit.
    3. Logs audit entry (is_gated=True).
    4. Returns updated state — gate_decision() will route from here.
    """

    session_id = state["session_id"]
    user_id    = state["user_id"]

    # find the initiate_checkout tool_call_id from the last AI message
    last_ai_message=state['messages'][-1]
    checkout_call=next(
        (tc for tc in last_ai_message.tool_calls if tc['name']=='initiate_checkout'),
        None,
    )
    tool_call_id=checkout_call['id'] if checkout_call else "unknown"

    # 1. get cart total
    cart=inventory_service.cart_get(session_id)
    grand_total=cart.get('grand_total',0.0)
    item_count=cart.get('total_items_count',0)

    # 2. verify spend permission
    check=user_service.verify_agent_spend_permission(user_id,grand_total)
    allowed=check.get('allowed',False)
    reason=check.get('reason',"")

    # 3. Audit log (is_gated=True marks this is a trust & safety checkpoint)
    user_service.log_agent_audit(
        session_id=session_id,
        action_type='PAYMENT_GATE_CHECK',
        reasoning=reason,
        payload={
            'cart_total': grand_total,
            'item_count': item_count,
            'allowed': allowed,
            'spend_limit': check.get("spend_limit"),
        },
        user_id=user_id,
        is_gated=True,
        user_confirmed=allowed,
    )

    if allowed:
        # Approved: return a ToolMessage so gate_decision can route to payment_tools.
        gate_msg = ToolMessage(
            content=json.dumps({
                "gate": "approved",
                "grand_total": grand_total,
                "reason": reason,
            }),
            tool_call_id=tool_call_id,
            name="initiate_checkout",
        )
        return {"messages": [gate_msg]}

    else:
        # Blocked: synthesise the rejection response directly here.
        # We return BOTH a ToolMessage (to close the open tool call in history)
        # and an AIMessage (the actual user-facing reply).
        # gate_decision will then route to END — no LLM call needed.
        # This avoids the Gemini "model prefilling" error that occurs when the
        # LLM is invoked with an AIMessage as the final message in history.
        spend_limit = check.get("spend_limit", 0.0) or 0.0

        gate_msg = ToolMessage(
            content=json.dumps({
                "gate": "blocked",
                "reason": reason,
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
def payment_tools_node(state: AgentState)-> dict:
    """
    Runs only after payment_gate approves.
    1. Fetches user profile + address.
    2. Creates order record in users.db.
    3. Generates Razorpay payment link.
    4. Binds link to order.
    5. Returns AIMessage with payment URL.
    """
    session_id = state["session_id"]
    user_id    = state["user_id"]

    # 1. get user profile and cart
    user=user_service.get_user_by_id(user_id) or {}
    cart=inventory_service.cart_get(session_id)
    address=user_service.get_user_default_address(user_id) or {}

    grand_total: float = float(cart.get("grand_total") or 0.0)

    # 2. create order
    order = user_service.create_order_from_cart(
        session_id=session_id,
        user_id=user_id,
        cart_data=cart,
        shipping_address_id=address.get("id")
    )

    # Guard: if order creation failed, abort early
    if not order.get("success"):
        error_msg = order.get("error", "Failed to create order.")
        return {
            "messages": [AIMessage(content=f"Couldn't create your order: {error_msg}")],
            "payment_status": "failed",
    }

    order_id= int(order["order_id"]) 
    order_number= str(order.get("order_number",f"ORD-{uuid.uuid4().hex[:8].upper()}"))

    # 3. generate razorpay payment link
    phone=user.get("phone","+910000000000")
    if not phone.startswith("+"):
        phone="+91"+phone.lstrip("0")

    link_result=create_payment_link(
        amount_inr=grand_total,
        description=f"FlowCart Order {order_number}",
        customer_name=user.get("full_name", "Customer"),
        customer_email=user.get("email", ""),
        customer_phone=phone,
        order_number=order_number,
    )

    # 4. bind payment to order and audit 
    if link_result.get("success"):
        payment_link_id=link_result['payment_link_id']
        short_url=link_result['short_url']

        # update order with razorpay link id
        user_service.link_razorpay_payment(
            order_id=order_id,                        
            payment_link_id=payment_link_id,
            razorpay_order_id=None,
        )

        # 5. return the payment link message to the agent 
        reply=AIMessage(content=(
            f"Your order **{order_number}** is confirmed!\n\n"
            f"**Order Total:** ₹{grand_total:,.2f}\n"
            f"**Delivering to:** {address.get('street_address', '')}, "
            f"{address.get('city', '')}\n\n"
            f"**Complete your payment here:**\n{short_url}\n\n"
            f"The link is valid for 24 hours. You'll get a confirmation SMS and email once paid."
        ))

    else:
        # payment link creation failed
        error=link_result.get("error","unknown error")

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
    llm=ChatGoogleGenerativeAI(
        model='gemini-3.5-flash-lite',
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




