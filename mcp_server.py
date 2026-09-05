"""
FlowCart Model Context Protocol (MCP) Server.
Exposes FlowCart's product discovery, cart management, and gated checkout
as standardized MCP tools so external AI buyers (like Claude Desktop)
can transact directly with the store.
"""

import os
import sys
import json
import uuid
from pathlib import Path
from typing import Optional

# Ensure project root is in sys.path
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mcp.server.fastmcp import FastMCP

from databases import inventory_service, user_service
from chat_agent.razorpay_client import execute_mandate_charge, create_payment_link

# Initialize FastMCP Server
mcp = FastMCP(
    name="FlowCart AI Commerce",
    instructions=(
        "FlowCart is an AI-native store selling electronics, smartphones, laptops, audio, "
        "and apparel with full-spec comparison and autonomous UPI Autopay checkout."
    )
)

@mcp.tool()
def search_products(
    query: str = "",
    category: Optional[str] = None,
    max_price: Optional[float] = None,
    min_price: Optional[float] = None,
    limit: int = 6,
) -> str:
    """
    Search the FlowCart store catalog by keyword, category, and price bounds.
    Categories: 'Mobiles & Accessories', 'Computers', 'Electronics & Gadgets', 'Clothing', 'Footwear'.
    Use short focused keywords like 'gaming', 'RTX 4050', '5500 mAh', 'ANC', 'marathon'.
    """
    results = inventory_service.search_products(
        query=query,
        category=category,
        max_price=max_price,
        min_price=min_price,
        limit=limit,
    )
    return json.dumps({
        "results_count": len(results),
        "products": results
    }, indent=2)


@mcp.tool()
def get_product_details(product_id_or_sku: str) -> str:
    """
    Retrieve comprehensive specifications, stock status, and all available variants
    (colors, sizes, storage, SKU IDs) for a specific product ID or SKU.
    """
    details = inventory_service.get_product_details(product_id_or_sku)
    if not details:
        return json.dumps({"error": f"Product '{product_id_or_sku}' not found."})
    return json.dumps(details, indent=2)


@mcp.tool()
def add_to_cart(
    variant_id: int,
    quantity: int = 1,
    session_id: str = "claude_ai_buyer"
) -> str:
    """
    Add a specific product variant by variant_id to the active shopping cart.
    Returns the updated cart summary.
    """
    res = inventory_service.cart_add(session_id=session_id, variant_id=variant_id, quantity=quantity)
    cart = inventory_service.cart_get(session_id=session_id)
    return json.dumps({
        "message": res.get("message", "Item added to cart"),
        "cart": cart
    }, indent=2)


@mcp.tool()
def view_cart(session_id: str = "claude_ai_buyer") -> str:
    """
    Inspect the active shopping cart contents, line items, subtotal, tax, and grand total.
    """
    cart = inventory_service.cart_get(session_id=session_id)
    return json.dumps(cart, indent=2)


@mcp.tool()
def clear_cart(session_id: str = "claude_ai_buyer") -> str:
    """
    Remove all items from the current active shopping cart.
    """
    res = inventory_service.cart_clear(session_id=session_id)
    return json.dumps(res, indent=2)


@mcp.tool()
def checkout_cart(
    session_id: str = "claude_ai_buyer",
    user_id: int = 1
) -> str:
    """
    Executes a secure, gated checkout for the active cart.
    
    1. If cart value is within pre-authorized limit AND all categories are whitelisted
       (e.g., Clothing/Footwear <= ₹4,000):
       Executes autonomous zero-click auto-debit via UPI Autopay mandate.
    
    2. If cart value exceeds limit OR contains high-ticket / non-whitelisted items
       (e.g., Laptops, Flagship phones):
       Gates the transaction and generates a real Razorpay payment link for manual authorization.
    """
    user = user_service.get_user_by_id(user_id)
    if not user:
        return json.dumps({"error": f"User ID {user_id} not found."})
    
    cart = inventory_service.cart_get(session_id)
    if not cart or not cart.get("items"):
        return json.dumps({"error": "Cannot checkout an empty cart."})
    
    grand_total = float(cart.get("grand_total") or 0.0)
    address = user_service.get_user_default_address(user_id) or {}
    
    # 1. Create order record
    order = user_service.create_order_from_cart(
        session_id=session_id,
        user_id=user_id,
        cart_data=cart,
        shipping_address_id=address.get("id"),
    )
    
    if not order.get("success"):
        return json.dumps({"error": order.get("error", "Failed to create order.")})
    
    order_id = int(order["order_id"])
    order_number = str(order.get("order_number", f"ORD-{uuid.uuid4().hex[:8].upper()}"))
    
    # 2. Check Mandate Guardrails
    mandate_check = user_service.verify_mandate_for_payment(user_id, cart)
    
    # PATH A: Zero-click Mandate Auto-Debit
    if mandate_check.get("allowed"):
        mandate = mandate_check.get("mandate", {})
        
        charge = execute_mandate_charge(
            amount_inr=grand_total,
            order_number=order_number,
            customer_id=mandate.get("razorpay_customer_id", ""),
            token_id=mandate.get("razorpay_token_id", ""),
            email=user.get("email", "buyer@flowcart.in"),
            phone=user.get("phone", "+919876543210"),
        )
        
        user_service.execute_mandate_payment(
            user_id=user_id,
            order_id=order_id,
            amount=grand_total,
            mandate_id=mandate.get("id", 1),
            session_id=session_id,
            razorpay_order_id=charge.get("razorpay_order_id"),
            real_payment_id=charge.get("payment_id"),
        )
        
        # Clear cart on successful auto-debit
        inventory_service.cart_clear(session_id)
        
        return json.dumps({
            "status": "COMPLETED",
            "payment_method": "UPI_AUTOPAY_MANDATE",
            "order_number": order_number,
            "order_id": order_id,
            "amount_paid": grand_total,
            "razorpay_order_id": charge.get("razorpay_order_id"),
            "shipping_address": address.get("address_line1", "Default Address"),
            "message": "✅ Payment debited autonomously via pre-authorized UPI Autopay mandate. Order confirmed!"
        }, indent=2)
    
    # PATH B: Gated Razorpay Payment Link
    else:
        link_res = create_payment_link(
            amount_inr=grand_total,
            description=f"FlowCart Order {order_number}",
            customer_name=user.get("name", "Customer"),
            customer_email=user.get("email", "buyer@flowcart.in"),
            customer_phone=user.get("phone", "+919876543210"),
            order_number=order_number,
        )
        
        if not link_res.get("success"):
            return json.dumps({
                "status": "ERROR",
                "error": link_res.get("error", "Failed to generate payment link.")
            })
        
        user_service.link_razorpay_payment(
            order_id=order_id,
            payment_link_id=link_res["payment_link_id"],
            razorpay_order_id=link_res.get("razorpay_order_id"),
        )
        
        return json.dumps({
            "status": "ACTION_REQUIRED",
            "payment_method": "RAZORPAY_PAYMENT_LINK",
            "order_number": order_number,
            "order_id": order_id,
            "amount_due": grand_total,
            "gate_reason": mandate_check.get("reason"),
            "payment_link_url": link_res.get("short_url"),
            "message": (
                f"⚠️ Autonomous debit gated: {mandate_check.get('reason')}. "
                f"Please authorize payment securely using the link: {link_res.get('short_url')}"
            )
        }, indent=2)


if __name__ == "__main__":
    # Runs standard FastMCP stdio server for Claude Desktop / MCP hosts
    mcp.run()
