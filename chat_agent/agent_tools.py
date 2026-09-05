"""
chat_agent/agent_tools.py
─────────────────────────
Phase 1 — LangChain @tool wrappers for the conversational checkout agent.

Tools 1-5:
  1. search_catalog            -> inventory_service.search_products()
  2. get_product_info          -> inventory_service.get_product_details()
  3. check_stock_availability  -> inventory_service.check_stock()
  4. add_to_cart               -> inventory_service.cart_add()
  5. view_cart                 -> inventory_service.cart_get()

Every tool execution is logged to agent_audit_logs via
user_service.log_agent_audit() for the evaluator audit trail.
"""

import json
import sys
from pathlib import Path
from typing import Optional

from langchain_core.tools import tool

# -- Path resolution: allow imports from the project root ---------------------
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import databases.inventory_service as inventory_service
import databases.user_service as user_service


# ----------------------------------------------------------------------------
# Helper: centralised audit logging
# ----------------------------------------------------------------------------

def _audit(
    session_id: str,
    action_type: str,
    reasoning: str,
    payload: dict,
    user_id: Optional[int] = None,
    is_gated: bool = False,
    user_confirmed: bool = False,
) -> None:
    """Fire-and-forget audit log entry. Swallows errors so tools never fail due to logging."""
    try:
        user_service.log_agent_audit(
            session_id=session_id,
            action_type=action_type,
            reasoning=reasoning,
            payload=payload,
            user_id=user_id,
            is_gated=is_gated,
            user_confirmed=user_confirmed,
        )
    except Exception:
        pass  # audit must never block the tool response


# ============================================================================
# Tool 1 -- search_catalog
# ============================================================================

@tool
def search_catalog(
    query: str = "",
    category: Optional[str] = None,
    max_price: Optional[float] = None,
    min_price: Optional[float] = None,
    color: Optional[str] = None,
    size: Optional[str] = None,
    limit: int = 8,
    session_id: str = "default",
    user_id: Optional[int] = None,
) -> str:
    """
    Search the product catalog by keyword, category, price range, color, or size.

    Use this tool FIRST whenever the user asks to find, browse, or filter
    products. Never fabricate product names or prices -- always call this tool.

    Categories available:
    - "Mobiles & Accessories" (Smartphones, chargers, cases)
    - "Computers" (Gaming laptops, ultrabooks, MacBooks)
    - "Electronics & Gadgets" (ANC headphones, earbuds, mice, keyboards, SSDs)
    - "Clothing" (T-shirts, gym wear, hoodies, jeans)
    - "Footwear" (Marathon running shoes, sneakers)

    Args:
        query:      Short, focused keyword(s) to search (e.g. "gaming", "RTX 4050", "iPhone", "marathon", "5000 mAh").
                    DO NOT pass long conversational phrases or questions here.
        category:   Category filter (e.g. "Computers", "Mobiles & Accessories").
        max_price:  Optional upper price bound in INR.
        min_price:  Optional lower price bound in INR.
        color:      Optional color filter.
        size:       Optional size filter (e.g. "M", "10", "128GB", "512GB").
        limit:      Maximum number of results to return (default 8).
        session_id: The current chat session ID (used for audit logging).
        user_id:    The logged-in user's ID (used for audit logging).

    Returns:
        JSON string with a list of matching products, each including variants,
        technical specifications in description, price, rating, and category.
    """
    results = inventory_service.search_products(
        query=query,
        category=category,
        max_price=max_price,
        min_price=min_price,
        color=color,
        size=size,
        limit=limit,
    )

    _audit(
        session_id=session_id,
        action_type="CATALOG_SEARCH",
        reasoning=f"User searched: query='{query}' category='{category}' max_price={max_price}",
        payload={
            "query": query,
            "category": category,
            "max_price": max_price,
            "min_price": min_price,
            "color": color,
            "size": size,
            "results_count": len(results),
        },
        user_id=user_id,
    )

    return json.dumps({
        "results_count": len(results),
        "products": results,
    })


# ============================================================================
# Tool 2 -- get_product_info
# ============================================================================

@tool
def get_product_info(
    product_id_or_sku: str,
    session_id: str = "default",
    user_id: Optional[int] = None,
) -> str:
    """
    Get full details and all available variants for a specific product.

    Use this tool when the user asks for more information about a specific
    product they already found, or when you need variant IDs to add to cart.
    Accepts either a numeric product ID or a variant SKU string.

    Args:
        product_id_or_sku: The product's integer ID or a variant SKU string.
        session_id:        The current chat session ID (used for audit logging).
        user_id:           The logged-in user's ID (used for audit logging).

    Returns:
        JSON string with complete product details: title, brand, category,
        description, base_price, rating, tags, and all variant specs
        (variant_id, sku, color, size, price, stock_quantity, image_url).
    """
    result = inventory_service.get_product_details(product_id_or_sku)

    _audit(
        session_id=session_id,
        action_type="PRODUCT_INFO",
        reasoning=f"Retrieved details for product/sku: {product_id_or_sku}",
        payload={
            "product_id_or_sku": product_id_or_sku,
            "found": result is not None,
        },
        user_id=user_id,
    )

    if result is None:
        return json.dumps({"error": f"No product found for identifier '{product_id_or_sku}'."})

    return json.dumps(result)


# ============================================================================
# Tool 3 -- check_stock_availability
# ============================================================================

@tool
def check_stock_availability(
    variant_id_or_sku: str,
    session_id: str = "default",
    user_id: Optional[int] = None,
) -> str:
    """
    Check the current stock level for a specific product variant.

    Use this tool before adding an item to cart if the user asks whether
    something is available, or after a failed add_to_cart to diagnose the issue.
    Accepts either a numeric variant ID or a variant SKU string.

    Args:
        variant_id_or_sku: The variant's integer ID or SKU string.
        session_id:        The current chat session ID (used for audit logging).
        user_id:           The logged-in user's ID (used for audit logging).

    Returns:
        JSON string with variant details including stock_quantity, color, size,
        price, and product title. Returns an error key if the variant is not found.
    """
    result = inventory_service.check_stock(variant_id_or_sku)

    _audit(
        session_id=session_id,
        action_type="STOCK_CHECK",
        reasoning=f"Checked stock for variant: {variant_id_or_sku}",
        payload={
            "variant_id_or_sku": variant_id_or_sku,
            "stock_quantity": result.get("stock_quantity") if "error" not in result else None,
        },
        user_id=user_id,
    )

    return json.dumps(result)


# ============================================================================
# Tool 4 -- add_to_cart
# ============================================================================

@tool
def add_to_cart(
    variant_id: int,
    quantity: int = 1,
    session_id: str = "default",
    user_id: Optional[int] = None,
) -> str:
    """
    Add a specific product variant to the user's shopping cart.

    Always use get_product_info first to find the correct variant_id for the
    color and size the user wants. Do NOT guess variant IDs.

    Args:
        variant_id:  The integer ID of the exact product variant to add.
                     (Obtain this from search_catalog or get_product_info.)
        quantity:    How many units to add (default 1).
        session_id:  The current chat session ID -- this is the cart key.
        user_id:     The logged-in user's ID (used for audit logging).

    Returns:
        JSON string with success status, a confirmation message, and the
        item details (title, color, size, unit_price, quantity_added).
        On failure, returns success=False and an error message explaining
        why (e.g. insufficient stock, variant not found).
    """
    result = inventory_service.cart_add(
        session_id=session_id,
        variant_id=variant_id,
        quantity=quantity,
    )

    _audit(
        session_id=session_id,
        action_type="CART_ADD",
        reasoning=f"Adding variant_id={variant_id} qty={quantity} to cart",
        payload={
            "variant_id": variant_id,
            "quantity": quantity,
            "success": result.get("success", False),
            "item": result.get("item"),
            "error": result.get("error"),
        },
        user_id=user_id,
    )

    return json.dumps(result)


# ============================================================================
# Tool 5 -- view_cart
# ============================================================================

@tool
def view_cart(
    session_id: str = "default",
    user_id: Optional[int] = None,
) -> str:
    """
    Retrieve the full contents of the user's current shopping cart.

    Use this tool whenever the user asks "what's in my cart?", before
    presenting an order summary, or before initiating checkout.

    Args:
        session_id: The current chat session ID -- the cart is keyed to this.
        user_id:    The logged-in user's ID (used for audit logging).

    Returns:
        JSON string containing: session_id, list of cart items (each with
        title, brand, sku, color, size, unit_price, quantity, item_total,
        in_stock flag), total_items_count, subtotal, tax (8%), and grand_total.
        Returns an empty items list if the cart is empty.
    """
    cart = inventory_service.cart_get(session_id=session_id)

    _audit(
        session_id=session_id,
        action_type="CART_VIEW",
        reasoning="User requested cart contents",
        payload={
            "total_items_count": cart.get("total_items_count", 0),
            "grand_total": cart.get("grand_total", 0.0),
        },
        user_id=user_id,
    )

    return json.dumps(cart)


# Tool-6: Remove from cart 
@tool
def remove_from_cart(
    cart_item_id: int,
    session_id: str = "default",
    user_id: Optional[int] = None,
) -> str:
    """
    Remove a specific item from the user's shopping cart by its cart_item_id.
    Use view_cart first to get the cart_item_id for the item the user
    wants to remove. Do NOT use the variant_id or product_id here.
    Args:
        cart_item_id: The integer ID of the cart row to remove.
                      (Obtain this from view_cart -> items[n]["cart_item_id"].)
        session_id:   The current chat session ID.
        user_id:      The logged-in user's ID (used for audit logging).
    Returns:
        JSON string with success=True if the item was found and removed,
        or success=False if the cart_item_id did not exist in this session.
    """
    result = inventory_service.cart_remove(
        session_id=session_id,
        cart_item_id=cart_item_id,
    )
    _audit(
        session_id=session_id,
        action_type="CART_REMOVE",
        reasoning=f"Removing cart_item_id={cart_item_id} from cart",
        payload={
            "cart_item_id": cart_item_id,
            "success": result.get("success", False),
        },
        user_id=user_id,
    )
    return json.dumps(result)


#Tool-7: Clear cart
@tool
def clear_cart(
    session_id: str='default',
    user_id: Optional[int]=None,
)-> str:
    """
    Wipe all the items in the user's shopping cart in one go.

    Use this only when the user explicitly asks to clear or empty their entire cart. For removing a single item, use remove_from_cart instead.

    Args:
        session_id: The current chat session ID.
        user_id: The logged-in user's ID (used for audit logging)

    Returns:
        JSON string with success=True confirming the cart has been cleared.

    """

    result=inventory_service.cart_clear(session_id=session_id)

    _audit(
        session_id=session_id,
        action_type="CART_CLEAR",
        reasoning='Useer requested full cart clear',
        payload={"success": result.get("success",False)},
        user_id=user_id,
    )

    return json.dumps(result)


# Tool 9: get_delivery_address
@tool
def get_delivery_address(
    user_id: int,
    session_id: str = "default",
) -> str:
    """
    Retrieve the user's default shipping address for order confirmation.

    Use this before initiating checkout so you can confirm the delivery
    address with the user. Falls back to any registered address if no
    default is set.

    Args:
        user_id:    The logged-in user's integer ID.
        session_id: The current chat session ID (used for audit logging).

    Returns:
        JSON string with: id, label, recipient_name, phone, street_address,
        city, state, postal_code, is_default.
        Returns an error key if no address is registered.
    """
    result = user_service.get_user_default_address(user_id)

    _audit(
        session_id=session_id,
        action_type="DELIVERY_ADDRESS",
        reasoning=f"Fetched default delivery address for user_id={user_id}",
        payload={
            "user_id": user_id,
            "found": result is not None,
        },
        user_id=user_id,
    )

    if result is None:
        return json.dumps({"error": f"No delivery address found for user_id={user_id}."})

    return json.dumps(result)


# Tool 10: get_order_history
@tool
def get_order_history(
    user_id: int,
    limit: int = 5,
    session_id: str = "default",
) -> str:
    """
    Fetch the user's past orders for context during the conversation.

    Use this when the user asks about a previous purchase, wants to
    reorder something, or when you need order IDs for payment status checks.

    Args:
        user_id:    The logged-in user's integer ID.
        limit:      Maximum number of recent orders to return (default 5).
        session_id: The current chat session ID (used for audit logging).

    Returns:
        JSON string with a list of past orders, each containing: order_number,
        grand_total, currency, order_status, payment_status, created_at,
        and a list of items (title, sku, color, size, quantity, unit_price).
    """
    import sqlite3

    conn = user_service.get_user_db()
    cursor = conn.cursor()

    # Fetch recent orders for the user
    cursor.execute(
        """
        SELECT id, order_number, grand_total, currency,
               order_status, payment_status, created_at
        FROM orders
        WHERE user_id = ?
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (user_id, limit),
    )
    order_rows = cursor.fetchall()

    orders = []
    for o in order_rows:
        cursor.execute(
            """
            SELECT title, sku, color, size, quantity, unit_price, total_price
            FROM order_items
            WHERE order_id = ?
            """,
            (o["id"],),
        )
        items = [dict(i) for i in cursor.fetchall()]
        orders.append({
            "order_number": o["order_number"],
            "grand_total": o["grand_total"],
            "currency": o["currency"],
            "order_status": o["order_status"],
            "payment_status": o["payment_status"],
            "created_at": o["created_at"],
            "items": items,
        })

    conn.close()

    _audit(
        session_id=session_id,
        action_type="ORDER_HISTORY",
        reasoning=f"Fetched last {limit} orders for user_id={user_id}",
        payload={
            "user_id": user_id,
            "orders_returned": len(orders),
        },
        user_id=user_id,
    )

    return json.dumps({
        "user_id": user_id,
        "orders_count": len(orders),
        "orders": orders,
    })


# Tool 11: initiate_checkout  [GATED — intercepted by payment_gate node]
@tool
def initiate_checkout(
    session_id: str = "default",
    user_id: Optional[int] = None,
) -> str:
    """
    Signal that the user is ready to check out and pay for their cart.

    IMPORTANT: This tool is intercepted by the payment_gate node in the
    LangGraph state machine BEFORE any payment action is taken. The gate
    will verify the cart total against the user's spend limit and either
    allow or block the transaction. Never call this tool speculatively --
    only call it after the user has explicitly confirmed they want to pay.

    Best practice before calling:
      1. Call view_cart to show the user a full order summary.
      2. Call get_delivery_address to confirm the shipping address.
      3. Ask the user: "Shall I proceed to checkout?"
      4. Only then call initiate_checkout.

    Args:
        session_id: The current chat session ID -- identifies which cart to check out.
        user_id:    The logged-in user's ID.

    Returns:
        A JSON string signalling checkout intent. The actual payment link
        is created by the payment_tools node after the gate approves.
    """
    _audit(
        session_id=session_id,
        action_type="CHECKOUT_INTENT",
        reasoning="User confirmed checkout intent -- forwarding to payment gate",
        payload={
            "session_id": session_id,
            "user_id": user_id,
        },
        user_id=user_id,
        is_gated=True,
    )

    # This return value is only reached if the graph somehow bypasses the gate.
    # In normal operation, payment_gate intercepts this tool call first.
    return json.dumps({
        "status": "pending_gate_check",
        "message": "Checkout request received. Verifying spend authorization...",
        "session_id": session_id,
    })

