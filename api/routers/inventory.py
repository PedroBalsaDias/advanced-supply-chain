"""
Inventory router for stock management.

Features:
- Real-time stock levels
- Stock updates with audit trail
- Low stock alerts
- Movement history
"""

from datetime import datetime, timedelta
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.routers.auth import get_current_user
from core.database import get_db_session
from core.logging import get_logger
from core.models import (
    Inventory,
    InventoryMovement,
    InventoryMovementType,
    Product,
    User,
)

logger = get_logger(__name__)
router = APIRouter()


# Schemas
class InventoryResponse(BaseModel):
    """Schema for inventory response."""
    id: UUID
    product_id: UUID
    product_sku: str
    product_name: str
    quantity_available: int
    quantity_reserved: int
    quantity_on_order: int
    quantity_total: int
    reorder_point: int
    reorder_quantity: int
    location: Optional[str]
    warehouse_id: Optional[str]
    is_low_stock: bool
    last_counted_at: Optional[str]
    updated_at: str
    
    class Config:
        from_attributes = True


class InventoryUpdate(BaseModel):
    """Schema for updating inventory quantity."""
    quantity_change: int = Field(..., description="Positive to add, negative to remove")
    movement_type: InventoryMovementType
    reference_type: Optional[str] = Field(None, description="e.g., 'order', 'adjustment'")
    reference_id: Optional[str] = None
    notes: Optional[str] = Field(None, max_length=500)


class InventoryMovementResponse(BaseModel):
    """Schema for inventory movement record."""
    id: UUID
    product_id: UUID
    product_sku: str
    product_name: str
    movement_type: InventoryMovementType
    quantity: int
    reference_type: Optional[str]
    reference_id: Optional[str]
    notes: Optional[str]
    performed_by: Optional[str]
    created_at: str
    
    class Config:
        from_attributes = True


class InventoryAdjustment(BaseModel):
    """Schema for manual inventory adjustment."""
    new_quantity: int = Field(..., ge=0, description="Target quantity after adjustment")
    reason: str = Field(..., min_length=1, max_length=500, description="Reason for adjustment")
    reference_type: Optional[str] = Field(None, description="e.g., 'cycle_count', 'damage'")
    reference_id: Optional[str] = None


class LowStockAlert(BaseModel):
    """Schema for low stock alert."""
    product_id: UUID
    product_sku: str
    product_name: str
    quantity_available: int
    reorder_point: int
    shortage: int


class ReorderSuggestion(BaseModel):
    """Schema for reorder suggestion."""
    product_id: UUID
    product_sku: str
    product_name: str
    current_stock: int
    suggested_quantity: int
    supplier_id: Optional[str]
    estimated_cost: Optional[float]


# Endpoints
@router.get("/levels", response_model=List[InventoryResponse])
async def get_inventory_levels(
    warehouse_id: Optional[str] = None,
    low_stock_only: bool = False,
    product_id: Optional[UUID] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user)
) -> List[dict]:
    """
    Get current inventory levels with filtering.
    
    Args:
        warehouse_id: Filter by warehouse
        low_stock_only: Show only items below reorder point
        product_id: Filter by specific product
        page: Page number
        page_size: Items per page
        db: Database session
        current_user: Authenticated user
        
    Returns:
        List[dict]: Inventory levels with product details
    """
    # Build query with joins
    query = (
        select(Inventory, Product)
        .join(Product, Inventory.product_id == Product.id)
        .where(Product.is_deleted == False)
    )
    
    # Apply filters
    if warehouse_id:
        query = query.where(Inventory.warehouse_id == warehouse_id)
    
    if product_id:
        query = query.where(Inventory.product_id == product_id)
    
    if low_stock_only:
        query = query.where(Inventory.quantity_available <= Inventory.reorder_point)
    
    # Pagination
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)
    
    result = await db.execute(query)
    rows = result.all()
    
    inventory_list = []
    for inventory, product in rows:
        inventory_list.append({
            "id": inventory.id,
            "product_id": inventory.product_id,
            "product_sku": product.sku,
            "product_name": product.name,
            "quantity_available": inventory.quantity_available,
            "quantity_reserved": inventory.quantity_reserved,
            "quantity_on_order": inventory.quantity_on_order,
            "quantity_total": inventory.quantity_total,
            "reorder_point": inventory.reorder_point,
            "reorder_quantity": inventory.reorder_quantity,
            "location": inventory.location,
            "warehouse_id": inventory.warehouse_id,
            "is_low_stock": inventory.is_low_stock,
            "last_counted_at": inventory.last_counted_at.isoformat() if inventory.last_counted_at else None,
            "updated_at": inventory.updated_at.isoformat() if inventory.updated_at else None
        })
    
    return inventory_list


@router.post("/update/{product_id}", response_model=InventoryResponse)
async def update_stock(
    product_id: UUID,
    update_data: InventoryUpdate,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user)
) -> dict:
    """
    Update stock quantity for a product.
    
    Args:
        product_id: Product UUID
        update_data: Update details including quantity change and reason
        db: Database session
        current_user: Authenticated user
        
    Returns:
        dict: Updated inventory state
        
    Raises:
        HTTPException: If insufficient stock or product not found
    """
    # Get inventory record
    result = await db.execute(
        select(Inventory, Product)
        .join(Product, Inventory.product_id == Product.id)
        .where(Inventory.product_id == product_id)
        .where(Product.is_deleted == False)
    )
    row = result.one_or_none()
    
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Inventory for product '{product_id}' not found"
        )
    
    inventory, product = row
    
    # Check for negative stock
    new_quantity = inventory.quantity_available + update_data.quantity_change
    if new_quantity < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Insufficient stock. Available: {inventory.quantity_available}, Requested: {abs(update_data.quantity_change)}"
        )
    
    # Update inventory
    inventory.quantity_available = new_quantity
    
    # Update reserved quantity for outbound movements
    if update_data.movement_type == InventoryMovementType.OUTBOUND:
        inventory.quantity_reserved = max(0, inventory.quantity_reserved + abs(update_data.quantity_change))
    elif update_data.movement_type == InventoryMovementType.INBOUND:
        inventory.quantity_on_order = max(0, inventory.quantity_on_order - abs(update_data.quantity_change))
    
    # Create movement record
    movement = InventoryMovement(
        product_id=product_id,
        movement_type=update_data.movement_type,
        quantity=update_data.quantity_change,
        reference_type=update_data.reference_type,
        reference_id=update_data.reference_id,
        notes=update_data.notes,
        performed_by=current_user.email
    )
    db.add(movement)
    
    await db.commit()
    await db.refresh(inventory)
    
    logger.info(
        "Stock updated",
        product_id=str(product_id),
        quantity_change=update_data.quantity_change,
        new_quantity=new_quantity,
        movement_type=update_data.movement_type.value
    )
    
    return {
        "id": inventory.id,
        "product_id": inventory.product_id,
        "product_sku": product.sku,
        "product_name": product.name,
        "quantity_available": inventory.quantity_available,
        "quantity_reserved": inventory.quantity_reserved,
        "quantity_on_order": inventory.quantity_on_order,
        "quantity_total": inventory.quantity_total,
        "reorder_point": inventory.reorder_point,
        "reorder_quantity": inventory.reorder_quantity,
        "location": inventory.location,
        "warehouse_id": inventory.warehouse_id,
        "is_low_stock": inventory.is_low_stock,
        "last_counted_at": inventory.last_counted_at.isoformat() if inventory.last_counted_at else None,
        "updated_at": inventory.updated_at.isoformat() if inventory.updated_at else None
    }


@router.post("/adjust/{product_id}", response_model=InventoryResponse)
async def adjust_inventory(
    product_id: UUID,
    adjustment: InventoryAdjustment,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user)
) -> dict:
    """
    Manually adjust inventory to a specific quantity.
    
    Args:
        product_id: Product UUID
        adjustment: Adjustment details with target quantity
        db: Database session
        current_user: Authenticated user
        
    Returns:
        dict: Updated inventory state
    """
    # Get inventory record
    result = await db.execute(
        select(Inventory, Product)
        .join(Product, Inventory.product_id == Product.id)
        .where(Inventory.product_id == product_id)
        .where(Product.is_deleted == False)
    )
    row = result.one_or_none()
    
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Inventory for product '{product_id}' not found"
        )
    
    inventory, product = row
    
    # Calculate adjustment
    quantity_difference = adjustment.new_quantity - inventory.quantity_available
    
    # Update inventory
    inventory.quantity_available = adjustment.new_quantity
    inventory.last_counted_at = datetime.utcnow()
    
    # Create movement record for the adjustment
    movement = InventoryMovement(
        product_id=product_id,
        movement_type=InventoryMovementType.ADJUSTMENT,
        quantity=quantity_difference,
        reference_type=adjustment.reference_type or "manual_adjustment",
        reference_id=adjustment.reference_id,
        notes=adjustment.reason,
        performed_by=current_user.email
    )
    db.add(movement)
    
    await db.commit()
    await db.refresh(inventory)
    
    logger.info(
        "Inventory adjusted",
        product_id=str(product_id),
        old_quantity=adjustment.new_quantity - quantity_difference,
        new_quantity=adjustment.new_quantity,
        reason=adjustment.reason
    )
    
    return {
        "id": inventory.id,
        "product_id": inventory.product_id,
        "product_sku": product.sku,
        "product_name": product.name,
        "quantity_available": inventory.quantity_available,
        "quantity_reserved": inventory.quantity_reserved,
        "quantity_on_order": inventory.quantity_on_order,
        "quantity_total": inventory.quantity_total,
        "reorder_point": inventory.reorder_point,
        "reorder_quantity": inventory.reorder_quantity,
        "location": inventory.location,
        "warehouse_id": inventory.warehouse_id,
        "is_low_stock": inventory.is_low_stock,
        "last_counted_at": inventory.last_counted_at.isoformat() if inventory.last_counted_at else None,
        "updated_at": inventory.updated_at.isoformat() if inventory.updated_at else None
    }


@router.get("/movements/{product_id}", response_model=List[InventoryMovementResponse])
async def get_movement_history(
    product_id: UUID,
    movement_type: Optional[InventoryMovementType] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user)
) -> List[dict]:
    """
    Get inventory movement history for a product.
    
    Args:
        product_id: Product UUID
        movement_type: Filter by movement type
        start_date: Filter from date
        end_date: Filter to date
        limit: Maximum records to return
        db: Database session
        current_user: Authenticated user
        
    Returns:
        List[dict]: Movement history
    """
    # Verify product exists
    product_result = await db.execute(
        select(Product).where(Product.id == product_id, Product.is_deleted == False)
    )
    product = product_result.scalar_one_or_none()
    
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product '{product_id}' not found"
        )
    
    # Build query
    query = (
        select(InventoryMovement, Product)
        .join(Product, InventoryMovement.product_id == Product.id)
        .where(InventoryMovement.product_id == product_id)
        .order_by(desc(InventoryMovement.created_at))
        .limit(limit)
    )
    
    # Apply filters
    if movement_type:
        query = query.where(InventoryMovement.movement_type == movement_type)
    
    if start_date:
        query = query.where(InventoryMovement.created_at >= start_date)
    
    if end_date:
        query = query.where(InventoryMovement.created_at <= end_date)
    
    result = await db.execute(query)
    rows = result.all()
    
    movements = []
    for movement, prod in rows:
        movements.append({
            "id": movement.id,
            "product_id": movement.product_id,
            "product_sku": prod.sku,
            "product_name": prod.name,
            "movement_type": movement.movement_type,
            "quantity": movement.quantity,
            "reference_type": movement.reference_type,
            "reference_id": movement.reference_id,
            "notes": movement.notes,
            "performed_by": movement.performed_by,
            "created_at": movement.created_at.isoformat() if movement.created_at else None
        })
    
    return movements


@router.get("/alerts/low-stock", response_model=List[LowStockAlert])
async def get_low_stock_alerts(
    critical_only: bool = False,
    warehouse_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user)
) -> List[dict]:
    """
    Get low stock alerts for products below reorder point.
    
    Args:
        critical_only: Show only critical (quantity = 0)
        warehouse_id: Filter by warehouse
        db: Database session
        current_user: Authenticated user
        
    Returns:
        List[dict]: Low stock alerts
    """
    query = (
        select(Inventory, Product)
        .join(Product, Inventory.product_id == Product.id)
        .where(Product.is_deleted == False)
        .where(Inventory.quantity_available <= Inventory.reorder_point)
    )
    
    if critical_only:
        query = query.where(Inventory.quantity_available == 0)
    
    if warehouse_id:
        query = query.where(Inventory.warehouse_id == warehouse_id)
    
    query = query.order_by(Inventory.quantity_available)
    
    result = await db.execute(query)
    rows = result.all()
    
    alerts = []
    for inventory, product in rows:
        shortage = max(0, inventory.reorder_point - inventory.quantity_available)
        alerts.append({
            "product_id": product.id,
            "product_sku": product.sku,
            "product_name": product.name,
            "quantity_available": inventory.quantity_available,
            "reorder_point": inventory.reorder_point,
            "shortage": shortage
        })
    
    return alerts


@router.get("/suggestions/reorder", response_model=List[ReorderSuggestion])
async def get_reorder_suggestions(
    warehouse_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user)
) -> List[dict]:
    """
    Get product reorder suggestions based on stock levels.
    
    Args:
        warehouse_id: Filter by warehouse
        db: Database session
        current_user: Authenticated user
        
    Returns:
        List[dict]: Reorder suggestions
    """
    query = (
        select(Inventory, Product)
        .join(Product, Inventory.product_id == Product.id)
        .where(Product.is_deleted == False)
        .where(Inventory.quantity_available <= Inventory.reorder_point)
    )
    
    if warehouse_id:
        query = query.where(Inventory.warehouse_id == warehouse_id)
    
    result = await db.execute(query)
    rows = result.all()
    
    suggestions = []
    for inventory, product in rows:
        suggested_qty = inventory.reorder_quantity
        estimated_cost = (product.unit_cost or 0) * suggested_qty
        
        suggestions.append({
            "product_id": product.id,
            "product_sku": product.sku,
            "product_name": product.name,
            "current_stock": inventory.quantity_available,
            "suggested_quantity": suggested_qty,
            "supplier_id": product.supplier_id,
            "estimated_cost": estimated_cost if product.unit_cost else None
        })
    
    return suggestions


@router.get("/dashboard/summary")
async def get_inventory_summary(
    warehouse_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user)
) -> dict:
    """
    Get inventory dashboard summary statistics.
    
    Args:
        warehouse_id: Filter by warehouse
        db: Database session
        current_user: Authenticated user
        
    Returns:
        dict: Summary statistics
    """
    # Base query
    base_query = select(Inventory).join(Product, Inventory.product_id == Product.id).where(Product.is_deleted == False)
    if warehouse_id:
        base_query = base_query.where(Inventory.warehouse_id == warehouse_id)
    
    # Total products in inventory
    total_result = await db.execute(select(func.count()).select_from(base_query.subquery()))
    total_products = total_result.scalar()
    
    # Total units
    units_result = await db.execute(
        select(func.sum(Inventory.quantity_available)).select_from(base_query.subquery())
    )
    total_units = units_result.scalar() or 0
    
    # Low stock count
    low_stock_result = await db.execute(
        select(func.count())
        .select_from(base_query.where(Inventory.quantity_available <= Inventory.reorder_point).subquery())
    )
    low_stock_count = low_stock_result.scalar()
    
    # Out of stock count
    out_of_stock_result = await db.execute(
        select(func.count())
        .select_from(base_query.where(Inventory.quantity_available == 0).subquery())
    )
    out_of_stock_count = out_of_stock_result.scalar()
    
    # Recent movements (last 24 hours)
    yesterday = datetime.utcnow() - timedelta(days=1)
    movements_result = await db.execute(
        select(func.count(InventoryMovement.id))
        .where(InventoryMovement.created_at >= yesterday)
    )
    recent_movements = movements_result.scalar()
    
    return {
        "total_products": total_products,
        "total_units": total_units,
        "low_stock_count": low_stock_count,
        "out_of_stock_count": out_of_stock_count,
        "recent_movements_24h": recent_movements,
        "warehouse_id": warehouse_id
    }
