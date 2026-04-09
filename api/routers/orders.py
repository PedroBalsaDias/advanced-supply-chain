"""
Orders router for order management.

Features:
- Multi-channel order processing (Shopify, Amazon, Direct)
- Order lifecycle management
- Inventory reservation on order creation
- Order fulfillment tracking
"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.routers.auth import get_current_user
from core.database import get_db_session
from core.logging import get_logger
from core.models import (
    Inventory,
    InventoryMovement,
    InventoryMovementType,
    Order,
    OrderItem,
    OrderStatus,
    Product,
    User,
)

logger = get_logger(__name__)
router = APIRouter()


# Schemas
class OrderItemCreate(BaseModel):
    """Schema for creating order line item."""
    product_id: Optional[UUID] = None
    sku: str = Field(..., min_length=1, max_length=100)
    product_name: str = Field(..., min_length=1, max_length=255)
    quantity: int = Field(..., ge=1)
    unit_price: float = Field(..., ge=0)


class OrderItemResponse(BaseModel):
    """Schema for order item response."""
    id: UUID
    product_id: Optional[UUID]
    sku: str
    product_name: str
    quantity: int
    unit_price: float
    total_price: float


class OrderCreate(BaseModel):
    """Schema for creating a new order."""
    order_number: Optional[str] = Field(None, max_length=50)
    external_id: Optional[str] = Field(None, max_length=100, description="External platform order ID")
    channel: str = Field(default="direct", max_length=50)
    customer_email: Optional[EmailStr] = None
    customer_name: Optional[str] = Field(None, max_length=255)
    shipping_address: Optional[dict] = None
    currency: str = Field(default="BRL", max_length=3)
    notes: Optional[str] = Field(None, max_length=1000)
    items: List[OrderItemCreate] = Field(..., min_items=1)


class OrderUpdate(BaseModel):
    """Schema for updating order."""
    status: Optional[OrderStatus] = None
    customer_email: Optional[EmailStr] = None
    customer_name: Optional[str] = Field(None, max_length=255)
    shipping_address: Optional[dict] = None
    notes: Optional[str] = Field(None, max_length=1000)
    tracking_number: Optional[str] = Field(None, max_length=100)


class OrderResponse(BaseModel):
    """Schema for order response."""
    id: UUID
    order_number: str
    external_id: Optional[str]
    channel: str
    status: OrderStatus
    customer_email: Optional[str]
    customer_name: Optional[str]
    shipping_address: Optional[dict]
    total_amount: Optional[float]
    currency: str
    notes: Optional[str]
    processed_at: Optional[str]
    shipped_at: Optional[str]
    items: List[OrderItemResponse]
    created_at: str
    updated_at: str


class OrderListResponse(BaseModel):
    """Paginated order list response."""
    items: List[OrderResponse]
    total: int
    page: int
    page_size: int
    pages: int


# Helper functions
async def generate_order_number(db: AsyncSession) -> str:
    """Generate unique order number (SC-YYYYMMDD-XXXX)."""
    today = datetime.utcnow()
    date_prefix = f"SC-{today.strftime('%Y%m%d')}"
    
    # Count orders today
    result = await db.execute(
        select(func.count(Order.id))
        .where(Order.order_number.like(f"{date_prefix}%"))
    )
    count = result.scalar() + 1
    
    return f"{date_prefix}-{count:04d}"


async def reserve_inventory(
    db: AsyncSession,
    product_id: UUID,
    quantity: int,
    order_id: str
) -> bool:
    """
    Reserve inventory for an order.
    
    Args:
        db: Database session
        product_id: Product UUID
        quantity: Quantity to reserve
        order_id: Order reference
        
    Returns:
        bool: True if reserved successfully
        
    Raises:
        HTTPException: If insufficient stock
    """
    result = await db.execute(
        select(Inventory).where(Inventory.product_id == product_id)
    )
    inventory = result.scalar_one_or_none()
    
    if not inventory:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Product {product_id} not found in inventory"
        )
    
    if inventory.quantity_available < quantity:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Insufficient stock for product {product_id}. Available: {inventory.quantity_available}"
        )
    
    # Reserve stock
    inventory.quantity_available -= quantity
    inventory.quantity_reserved += quantity
    
    # Create movement record
    movement = InventoryMovement(
        product_id=product_id,
        movement_type=InventoryMovementType.OUTBOUND,
        quantity=-quantity,
        reference_type="order",
        reference_id=order_id,
        notes=f"Reserved for order {order_id}"
    )
    db.add(movement)
    
    return True


async def release_inventory(
    db: AsyncSession,
    product_id: UUID,
    quantity: int,
    order_id: str
) -> None:
    """Release reserved inventory (e.g., on order cancellation)."""
    result = await db.execute(
        select(Inventory).where(Inventory.product_id == product_id)
    )
    inventory = result.scalar_one_or_none()
    
    if inventory:
        inventory.quantity_available += quantity
        inventory.quantity_reserved = max(0, inventory.quantity_reserved - quantity)
        
        movement = InventoryMovement(
            product_id=product_id,
            movement_type=InventoryMovementType.ADJUSTMENT,
            quantity=quantity,
            reference_type="order_cancel",
            reference_id=order_id,
            notes=f"Released reservation for cancelled order {order_id}"
        )
        db.add(movement)


# Endpoints
@router.post("", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def create_order(
    order_data: OrderCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user)
) -> Order:
    """
    Create a new order with inventory reservation.
    
    Args:
        order_data: Order creation data
        db: Database session
        current_user: Authenticated user
        
    Returns:
        Order: Created order
    """
    # Generate order number if not provided
    order_number = order_data.order_number or await generate_order_number(db)
    
    # Check for duplicate external_id
    if order_data.external_id:
        existing = await db.execute(
            select(Order).where(Order.external_id == order_data.external_id)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Order with external ID '{order_data.external_id}' already exists"
            )
    
    # Create order
    order = Order(
        order_number=order_number,
        external_id=order_data.external_id,
        channel=order_data.channel,
        status=OrderStatus.PENDING,
        customer_email=order_data.customer_email,
        customer_name=order_data.customer_name,
        shipping_address=order_data.shipping_address,
        currency=order_data.currency,
        notes=order_data.notes
    )
    db.add(order)
    await db.flush()  # Get order.id
    
    # Process items and reserve inventory
    total_amount = 0.0
    for item_data in order_data.items:
        # Find product by SKU if product_id not provided
        if not item_data.product_id:
            prod_result = await db.execute(
                select(Product).where(
                    Product.sku == item_data.sku,
                    Product.is_deleted == False
                )
            )
            product = prod_result.scalar_one_or_none()
            if product:
                item_data.product_id = product.id
        
        # Reserve inventory
        if item_data.product_id:
            await reserve_inventory(db, item_data.product_id, item_data.quantity, str(order.id))
        
        # Create order item
        total_price = item_data.quantity * item_data.unit_price
        total_amount += total_price
        
        order_item = OrderItem(
            order_id=order.id,
            product_id=item_data.product_id,
            sku=item_data.sku,
            product_name=item_data.product_name,
            quantity=item_data.quantity,
            unit_price=item_data.unit_price,
            total_price=total_price
        )
        db.add(order_item)
    
    order.total_amount = total_amount
    await db.commit()
    await db.refresh(order)
    
    logger.info(
        "Order created",
        order_id=str(order.id),
        order_number=order.order_number,
        channel=order.channel,
        total_amount=total_amount
    )
    
    return order


@router.get("", response_model=OrderListResponse)
async def list_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[OrderStatus] = None,
    channel: Optional[str] = None,
    customer_email: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user)
) -> dict:
    """
    List orders with filtering and pagination.
    
    Args:
        page: Page number
        page_size: Items per page
        status: Filter by status
        channel: Filter by channel
        customer_email: Filter by customer
        start_date: Filter from date
        end_date: Filter to date
        search: Search in order number
        db: Database session
        current_user: Authenticated user
        
    Returns:
        dict: Paginated order list
    """
    # Build query
    query = select(Order)
    filters = []
    
    if status:
        filters.append(Order.status == status)
    
    if channel:
        filters.append(Order.channel == channel)
    
    if customer_email:
        filters.append(Order.customer_email.ilike(f"%{customer_email}%"))
    
    if start_date:
        filters.append(Order.created_at >= start_date)
    
    if end_date:
        filters.append(Order.created_at <= end_date)
    
    if search:
        filters.append(
            or_(
                Order.order_number.ilike(f"%{search}%"),
                Order.external_id.ilike(f"%{search}%")
            )
        )
    
    if filters:
        query = query.where(and_(*filters))
    
    # Count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()
    
    # Pagination and ordering
    offset = (page - 1) * page_size
    query = query.order_by(desc(Order.created_at)).offset(offset).limit(page_size)
    
    result = await db.execute(query)
    orders = result.scalars().all()
    
    # Format response
    items = []
    for order in orders:
        items.append({
            "id": order.id,
            "order_number": order.order_number,
            "external_id": order.external_id,
            "channel": order.channel,
            "status": order.status,
            "customer_email": order.customer_email,
            "customer_name": order.customer_name,
            "shipping_address": order.shipping_address,
            "total_amount": order.total_amount,
            "currency": order.currency,
            "notes": order.notes,
            "processed_at": order.processed_at.isoformat() if order.processed_at else None,
            "shipped_at": order.shipped_at.isoformat() if order.shipped_at else None,
            "items": [
                {
                    "id": item.id,
                    "product_id": item.product_id,
                    "sku": item.sku,
                    "product_name": item.product_name,
                    "quantity": item.quantity,
                    "unit_price": item.unit_price,
                    "total_price": item.total_price
                }
                for item in order.items
            ],
            "created_at": order.created_at.isoformat() if order.created_at else None,
            "updated_at": order.updated_at.isoformat() if order.updated_at else None
        })
    
    pages = (total + page_size - 1) // page_size
    
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": pages
    }


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user)
) -> dict:
    """
    Get a single order by ID.
    
    Args:
        order_id: Order UUID
        db: Database session
        current_user: Authenticated user
        
    Returns:
        dict: Order details
    """
    result = await db.execute(
        select(Order).where(Order.id == order_id)
    )
    order = result.scalar_one_or_none()
    
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order '{order_id}' not found"
        )
    
    return {
        "id": order.id,
        "order_number": order.order_number,
        "external_id": order.external_id,
        "channel": order.channel,
        "status": order.status,
        "customer_email": order.customer_email,
        "customer_name": order.customer_name,
        "shipping_address": order.shipping_address,
        "total_amount": order.total_amount,
        "currency": order.currency,
        "notes": order.notes,
        "processed_at": order.processed_at.isoformat() if order.processed_at else None,
        "shipped_at": order.shipped_at.isoformat() if order.shipped_at else None,
        "items": [
            {
                "id": item.id,
                "product_id": item.product_id,
                "sku": item.sku,
                "product_name": item.product_name,
                "quantity": item.quantity,
                "unit_price": item.unit_price,
                "total_price": item.total_price
            }
            for item in order.items
        ],
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "updated_at": order.updated_at.isoformat() if order.updated_at else None
    }


@router.patch("/{order_id}/status", response_model=OrderResponse)
async def update_order_status(
    order_id: UUID,
    status_update: OrderUpdate,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user)
) -> dict:
    """
    Update order status and handle state transitions.
    
    Args:
        order_id: Order UUID
        status_update: Status update data
        db: Database session
        current_user: Authenticated user
        
    Returns:
        dict: Updated order
    """
    result = await db.execute(
        select(Order).where(Order.id == order_id)
    )
    order = result.scalar_one_or_none()
    
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order '{order_id}' not found"
        )
    
    if not status_update.status:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Status is required"
        )
    
    old_status = order.status
    new_status = status_update.status
    
    # State transition validation
    valid_transitions = {
        OrderStatus.PENDING: [OrderStatus.CONFIRMED, OrderStatus.CANCELLED],
        OrderStatus.CONFIRMED: [OrderStatus.PROCESSING, OrderStatus.CANCELLED],
        OrderStatus.PROCESSING: [OrderStatus.SHIPPED, OrderStatus.CANCELLED],
        OrderStatus.SHIPPED: [OrderStatus.DELIVERED],
        OrderStatus.DELIVERED: [OrderStatus.RETURNED],
    }
    
    if new_status not in valid_transitions.get(old_status, []):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status transition from {old_status.value} to {new_status.value}"
        )
    
    # Handle status-specific actions
    if new_status == OrderStatus.PROCESSING and old_status == OrderStatus.CONFIRMED:
        order.processed_at = datetime.utcnow()
    
    elif new_status == OrderStatus.SHIPPED:
        order.shipped_at = datetime.utcnow()
        # Release reservation, reduce stock permanently
        for item in order.items:
            if item.product_id:
                inv_result = await db.execute(
                    select(Inventory).where(Inventory.product_id == item.product_id)
                )
                inventory = inv_result.scalar_one_or_none()
                if inventory:
                    inventory.quantity_reserved = max(0, inventory.quantity_reserved - item.quantity)
    
    elif new_status == OrderStatus.CANCELLED:
        # Release all inventory reservations
        for item in order.items:
            if item.product_id:
                await release_inventory(db, item.product_id, item.quantity, str(order.id))
    
    order.status = new_status
    await db.commit()
    await db.refresh(order)
    
    logger.info(
        "Order status updated",
        order_id=str(order_id),
        old_status=old_status.value,
        new_status=new_status.value
    )
    
    return await get_order(order_id, db, current_user)


@router.get("/dashboard/summary")
async def get_orders_summary(
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user)
) -> dict:
    """
    Get orders dashboard summary.
    
    Args:
        db: Database session
        current_user: Authenticated user
        
    Returns:
        dict: Summary statistics
    """
    # Count by status
    status_counts = {}
    for status in OrderStatus:
        result = await db.execute(
            select(func.count(Order.id)).where(Order.status == status)
        )
        status_counts[status.value] = result.scalar()
    
    # Today's orders
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_result = await db.execute(
        select(func.count(Order.id)).where(Order.created_at >= today)
    )
    today_count = today_result.scalar()
    
    # Revenue today
    revenue_result = await db.execute(
        select(func.sum(Order.total_amount))
        .where(Order.created_at >= today)
        .where(Order.status != OrderStatus.CANCELLED)
    )
    today_revenue = revenue_result.scalar() or 0
    
    return {
        "total_orders": sum(status_counts.values()),
        "by_status": status_counts,
        "today_orders": today_count,
        "today_revenue": today_revenue
    }
