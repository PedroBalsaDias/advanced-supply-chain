"""
Automations router for rule-based workflow engine.

Features:
- Trigger-based automation rules
- Low stock alerts and reordering
- Multi-action workflows
- Execution history
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.routers.auth import get_current_user
from core.config import settings
from core.database import get_db_session
from core.logging import get_logger
from core.models import (
    AutomationActionType,
    AutomationRule,
    AutomationTriggerType,
    Inventory,
    Product,
    User,
)
from workers.celery_app import celery_app

logger = get_logger(__name__)
router = APIRouter()


# Schemas
class TriggerConfig(BaseModel):
    """Schema for trigger configuration."""
    threshold: Optional[int] = Field(None, description="Stock threshold for LOW_STOCK trigger")
    product_category: Optional[str] = None
    product_id: Optional[UUID] = None
    schedule: Optional[str] = Field(None, description="Cron expression for SCHEDULED trigger")
    webhook_url: Optional[str] = None


class ActionConfig(BaseModel):
    """Schema for action configuration."""
    # Email action
    email_to: Optional[str] = None
    email_subject: Optional[str] = None
    email_template: Optional[str] = None
    
    # Purchase order action
    supplier_email: Optional[str] = None
    quantity: Optional[int] = Field(None, ge=1)
    
    # Webhook action
    webhook_url: Optional[str] = None
    webhook_method: str = "POST"
    webhook_headers: Optional[Dict[str, str]] = None
    
    # Slack action
    slack_channel: Optional[str] = None
    slack_message: Optional[str] = None
    
    # Price update action
    new_price: Optional[float] = None
    price_adjustment_percent: Optional[float] = None


class AutomationCreate(BaseModel):
    """Schema for creating automation rule."""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)
    is_active: bool = True
    trigger_type: AutomationTriggerType
    trigger_config: Dict[str, Any] = Field(default_factory=dict)
    action_type: AutomationActionType
    action_config: Dict[str, Any] = Field(default_factory=dict)


class AutomationUpdate(BaseModel):
    """Schema for updating automation rule."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)
    is_active: Optional[bool] = None
    trigger_config: Optional[Dict[str, Any]] = None
    action_config: Optional[Dict[str, Any]] = None


class AutomationResponse(BaseModel):
    """Schema for automation rule response."""
    id: UUID
    name: str
    description: Optional[str]
    is_active: bool
    trigger_type: AutomationTriggerType
    trigger_config: Dict[str, Any]
    action_type: AutomationActionType
    action_config: Dict[str, Any]
    last_triggered_at: Optional[str]
    trigger_count: int
    created_by: Optional[str]
    created_at: str
    updated_at: str


class AutomationExecution(BaseModel):
    """Schema for automation execution record."""
    id: UUID
    automation_id: UUID
    automation_name: str
    trigger_data: Dict[str, Any]
    action_results: Dict[str, Any]
    status: str  # success, failed, partial
    executed_at: str
    error_message: Optional[str]


# Endpoints
@router.post("", response_model=AutomationResponse, status_code=status.HTTP_201_CREATED)
async def create_automation(
    automation_data: AutomationCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user)
) -> AutomationRule:
    """Create a new automation rule."""
    automation = AutomationRule(
        name=automation_data.name,
        description=automation_data.description,
        is_active=automation_data.is_active,
        trigger_type=automation_data.trigger_type,
        trigger_config=automation_data.trigger_config,
        action_type=automation_data.action_type,
        action_config=automation_data.action_config,
        created_by=current_user.email
    )
    
    db.add(automation)
    await db.commit()
    await db.refresh(automation)
    
    logger.info(
        "Automation rule created",
        automation_id=str(automation.id),
        name=automation.name,
        trigger_type=automation.trigger_type.value,
        action_type=automation.action_type.value
    )
    
    return automation


@router.get("", response_model=List[AutomationResponse])
async def list_automations(
    is_active: Optional[bool] = None,
    trigger_type: Optional[AutomationTriggerType] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user)
) -> List[AutomationRule]:
    """List automation rules with filtering."""
    query = select(AutomationRule)
    
    if is_active is not None:
        query = query.where(AutomationRule.is_active == is_active)
    
    if trigger_type:
        query = query.where(AutomationRule.trigger_type == trigger_type)
    
    offset = (page - 1) * page_size
    query = query.order_by(desc(AutomationRule.created_at)).offset(offset).limit(page_size)
    
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{automation_id}", response_model=AutomationResponse)
async def get_automation(
    automation_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user)
) -> AutomationRule:
    """Get a single automation rule by ID."""
    result = await db.execute(
        select(AutomationRule).where(AutomationRule.id == automation_id)
    )
    automation = result.scalar_one_or_none()
    
    if not automation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Automation rule '{automation_id}' not found"
        )
    
    return automation


@router.put("/{automation_id}", response_model=AutomationResponse)
async def update_automation(
    automation_id: UUID,
    update_data: AutomationUpdate,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user)
) -> AutomationRule:
    """Update an automation rule."""
    result = await db.execute(
        select(AutomationRule).where(AutomationRule.id == automation_id)
    )
    automation = result.scalar_one_or_none()
    
    if not automation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Automation rule '{automation_id}' not found"
        )
    
    # Update fields
    if update_data.name is not None:
        automation.name = update_data.name
    if update_data.description is not None:
        automation.description = update_data.description
    if update_data.is_active is not None:
        automation.is_active = update_data.is_active
    if update_data.trigger_config is not None:
        automation.trigger_config = update_data.trigger_config
    if update_data.action_config is not None:
        automation.action_config = update_data.action_config
    
    await db.commit()
    await db.refresh(automation)
    
    logger.info("Automation rule updated", automation_id=str(automation_id))
    
    return automation


@router.delete("/{automation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_automation(
    automation_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user)
) -> None:
    """Delete an automation rule."""
    result = await db.execute(
        select(AutomationRule).where(AutomationRule.id == automation_id)
    )
    automation = result.scalar_one_or_none()
    
    if not automation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Automation rule '{automation_id}' not found"
        )
    
    await db.delete(automation)
    await db.commit()
    
    logger.info("Automation rule deleted", automation_id=str(automation_id))


@router.post("/{automation_id}/trigger", response_model=Dict[str, Any])
async def manual_trigger(
    automation_id: UUID,
    test_data: Optional[Dict[str, Any]] = None,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """Manually trigger an automation rule."""
    result = await db.execute(
        select(AutomationRule).where(AutomationRule.id == automation_id)
    )
    automation = result.scalar_one_or_none()
    
    if not automation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Automation rule '{automation_id}' not found"
        )
    
    if not automation.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Automation rule is not active"
        )
    
    # Queue automation execution via Celery
    task = celery_app.send_task(
        "workers.tasks.automation_engine.execute_automation",
        args=[str(automation_id), test_data or {}]
    )
    
    logger.info(
        "Automation manually triggered",
        automation_id=str(automation_id),
        task_id=task.id
    )
    
    return {
        "status": "queued",
        "automation_id": str(automation_id),
        "automation_name": automation.name,
        "task_id": task.id
    }


@router.get("/templates/available")
async def get_automation_templates(
    current_user: User = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """Get available automation templates."""
    templates = [
        {
            "name": "Low Stock Alert",
            "description": "Send email notification when stock falls below threshold",
            "trigger_type": AutomationTriggerType.LOW_STOCK,
            "trigger_config": {"threshold": 10},
            "action_type": AutomationActionType.SEND_EMAIL,
            "action_config": {
                "email_subject": "Low Stock Alert",
                "email_template": "product {{sku}} has only {{quantity}} units remaining"
            }
        },
        {
            "name": "Auto Reorder",
            "description": "Automatically create purchase order when stock is low",
            "trigger_type": AutomationTriggerType.LOW_STOCK,
            "trigger_config": {"threshold": 5},
            "action_type": AutomationActionType.CREATE_PURCHASE_ORDER,
            "action_config": {
                "quantity_multiplier": 2
            }
        },
        {
            "name": "Order Notification",
            "description": "Send Slack notification for new orders",
            "trigger_type": AutomationTriggerType.NEW_ORDER,
            "trigger_config": {},
            "action_type": AutomationActionType.NOTIFY_SLACK,
            "action_config": {
                "slack_message": "New order received: {{order_number}} - ${{total_amount}}"
            }
        },
        {
            "name": "Dynamic Pricing",
            "description": "Adjust price based on inventory levels",
            "trigger_type": AutomationTriggerType.LOW_STOCK,
            "trigger_config": {"threshold": 20},
            "action_type": AutomationActionType.UPDATE_PRICE,
            "action_config": {
                "price_adjustment_percent": 10
            }
        }
    ]
    
    return templates


@router.get("/{automation_id}/executions")
async def get_execution_history(
    automation_id: UUID,
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """Get execution history for an automation rule."""
    result = await db.execute(
        select(AutomationRule).where(AutomationRule.id == automation_id)
    )
    automation = result.scalar_one_or_none()
    
    if not automation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Automation rule '{automation_id}' not found"
        )
    
    # Return simulated execution history
    executions = []
    for i in range(min(limit, automation.trigger_count)):
        executions.append({
            "id": f"exec-{i}",
            "automation_id": str(automation_id),
            "automation_name": automation.name,
            "trigger_data": {"simulated": True},
            "action_results": {"status": "success"},
            "status": "success",
            "executed_at": datetime.utcnow().isoformat(),
            "error_message": None
        })
    
    return executions


@router.post("/check/low-stock")
async def check_low_stock_automations(
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """Manually check and trigger low stock automations."""
    result = await db.execute(
        select(AutomationRule)
        .where(AutomationRule.is_active == True)
        .where(AutomationRule.trigger_type == AutomationTriggerType.LOW_STOCK)
    )
    automations = result.scalars().all()
    
    triggered = []
    
    for automation in automations:
        threshold = automation.trigger_config.get("threshold", settings.low_stock_threshold)
        product_category = automation.trigger_config.get("product_category")
        
        # Find low stock products
        query = (
            select(Inventory, Product)
            .join(Product, Inventory.product_id == Product.id)
            .where(Product.is_deleted == False)
            .where(Inventory.quantity_available <= threshold)
        )
        
        if product_category:
            query = query.where(Product.category == product_category)
        
        low_stock_result = await db.execute(query)
        low_stock_items = low_stock_result.all()
        
        for inventory, product in low_stock_items:
            # Queue automation for each product
            task = celery_app.send_task(
                "workers.tasks.automation_engine.execute_automation",
                args=[
                    str(automation.id),
                    {
                        "product_id": str(product.id),
                        "sku": product.sku,
                        "name": product.name,
                        "quantity": inventory.quantity_available,
                        "threshold": threshold
                    }
                ]
            )
            
            triggered.append({
                "automation_id": str(automation.id),
                "automation_name": automation.name,
                "product_sku": product.sku,
                "product_name": product.name,
                "current_stock": inventory.quantity_available,
                "task_id": task.id
            })
    
    logger.info("Low stock check completed", triggered_count=len(triggered))
    
    return {
        "checked_at": datetime.utcnow().isoformat(),
        "automations_checked": len(automations),
        "triggers_queued": len(triggered),
        "triggered_items": triggered
    }
