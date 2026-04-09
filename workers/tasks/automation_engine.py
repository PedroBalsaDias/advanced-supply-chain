"""
Automation engine task for executing automation rules.

Processes triggers and executes configured actions.
"""

import json
from datetime import datetime
from typing import Any, Dict
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from workers.celery_app import celery_app
from core.database import get_db_context
from core.logging import get_logger
from core.models import AutomationActionType, AutomationRule, Inventory, Product

logger = get_logger(__name__)


@celery_app.task(bind=True, max_retries=3)
def execute_automation(self, automation_id: str, trigger_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute an automation rule with given trigger data.
    
    Args:
        automation_id: UUID of automation rule
        trigger_data: Data from the trigger event
        
    Returns:
        dict: Execution results
    """
    logger.info(
        "Executing automation",
        automation_id=automation_id,
        trigger_data=trigger_data
    )
    
    try:
        # Run async code in sync context
        import asyncio
        return asyncio.run(_execute_automation_async(automation_id, trigger_data))
        
    except Exception as exc:
        logger.error("Automation execution failed", error=str(exc))
        raise self.retry(exc=exc, countdown=60)


async def _execute_automation_async(
    automation_id: str,
    trigger_data: Dict[str, Any]
) -> Dict[str, Any]:
    """Async implementation of automation execution."""
    
    async with get_db_context() as db:
        # Load automation rule
        result = await db.execute(
            select(AutomationRule).where(AutomationRule.id == UUID(automation_id))
        )
        automation = result.scalar_one_or_none()
        
        if not automation:
            raise ValueError(f"Automation {automation_id} not found")
        
        if not automation.is_active:
            return {"status": "skipped", "reason": "automation_inactive"}
        
        # Update automation stats
        automation.last_triggered_at = datetime.utcnow()
        automation.trigger_count += 1
        await db.commit()
        
        # Execute action based on type
        action_result = await _execute_action(
            db,
            automation.action_type,
            automation.action_config,
            trigger_data
        )
        
        logger.info(
            "Automation executed",
            automation_id=automation_id,
            action_type=automation.action_type.value,
            result=action_result
        )
        
        return {
            "status": "success",
            "automation_id": automation_id,
            "automation_name": automation.name,
            "action_type": automation.action_type.value,
            "action_result": action_result,
            "executed_at": datetime.utcnow().isoformat()
        }


async def _execute_action(
    db: AsyncSession,
    action_type: AutomationActionType,
    action_config: Dict[str, Any],
    trigger_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Execute a specific action type.
    
    Args:
        db: Database session
        action_type: Type of action to execute
        action_config: Action configuration
        trigger_data: Data from trigger
        
    Returns:
        dict: Action execution result
    """
    if action_type == AutomationActionType.SEND_EMAIL:
        return await _send_email_action(action_config, trigger_data)
    
    elif action_type == AutomationActionType.CREATE_PURCHASE_ORDER:
        return await _create_purchase_order_action(db, action_config, trigger_data)
    
    elif action_type == AutomationActionType.NOTIFY_SLACK:
        return await _notify_slack_action(action_config, trigger_data)
    
    elif action_type == AutomationActionType.CALL_WEBHOOK:
        return await _call_webhook_action(action_config, trigger_data)
    
    elif action_type == AutomationActionType.UPDATE_PRICE:
        return await _update_price_action(db, action_config, trigger_data)
    
    else:
        return {"status": "error", "message": f"Unknown action type: {action_type}"}


async def _send_email_action(
    config: Dict[str, Any],
    trigger_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Simulate sending an email.
    
    In production, use SMTP or email service (SendGrid, AWS SES).
    """
    to_email = config.get("email_to", "admin@company.com")
    subject = _render_template(config.get("email_subject", "Alert"), trigger_data)
    body = _render_template(config.get("email_template", ""), trigger_data)
    
    logger.info(
        "Email action simulated",
        to=to_email,
        subject=subject,
        body_preview=body[:100] if body else ""
    )
    
    return {
        "status": "simulated",
        "action": "send_email",
        "to": to_email,
        "subject": subject
    }


async def _create_purchase_order_action(
    db: AsyncSession,
    config: Dict[str, Any],
    trigger_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Simulate creating a purchase order.
    
    In production, integrate with supplier API or ERP system.
    """
    sku = trigger_data.get("sku", "UNKNOWN")
    current_quantity = trigger_data.get("quantity", 0)
    
    # Calculate order quantity
    multiplier = config.get("quantity_multiplier", 2)
    base_quantity = config.get("quantity", 100)
    order_quantity = max(base_quantity, current_quantity * multiplier)
    
    logger.info(
        "Purchase order simulated",
        sku=sku,
        quantity=order_quantity
    )
    
    return {
        "status": "simulated",
        "action": "create_purchase_order",
        "sku": sku,
        "quantity": order_quantity,
        "supplier_email": config.get("supplier_email")
    }


async def _notify_slack_action(
    config: Dict[str, Any],
    trigger_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Simulate sending Slack notification.
    
    In production, call Slack Web API.
    """
    channel = config.get("slack_channel", "#inventory-alerts")
    message = _render_template(config.get("slack_message", ""), trigger_data)
    
    logger.info(
        "Slack notification simulated",
        channel=channel,
        message=message
    )
    
    return {
        "status": "simulated",
        "action": "notify_slack",
        "channel": channel,
        "message": message
    }


async def _call_webhook_action(
    config: Dict[str, Any],
    trigger_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Call external webhook.
    
    Makes HTTP request to configured endpoint.
    """
    url = config.get("webhook_url")
    method = config.get("webhook_method", "POST")
    headers = config.get("webhook_headers", {})
    
    if not url:
        return {"status": "error", "message": "No webhook URL configured"}
    
    try:
        async with httpx.AsyncClient() as client:
            if method.upper() == "POST":
                response = await client.post(url, json=trigger_data, headers=headers)
            else:
                response = await client.get(url, headers=headers)
            
            return {
                "status": "success",
                "action": "call_webhook",
                "url": url,
                "response_status": response.status_code
            }
    except Exception as e:
        return {
            "status": "error",
            "action": "call_webhook",
            "error": str(e)
        }


async def _update_price_action(
    db: AsyncSession,
    config: Dict[str, Any],
    trigger_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Simulate updating product price.
    
    In production, update database and sync to channels.
    """
    product_id = trigger_data.get("product_id")
    adjustment = config.get("price_adjustment_percent", 0)
    
    logger.info(
        "Price update simulated",
        product_id=product_id,
        adjustment_percent=adjustment
    )
    
    return {
        "status": "simulated",
        "action": "update_price",
        "product_id": product_id,
        "adjustment_percent": adjustment
    }


def _render_template(template: str, data: Dict[str, Any]) -> str:
    """
    Simple template rendering using {{variable}} syntax.
    
    Args:
        template: Template string with {{placeholders}}
        data: Data dictionary for substitution
        
    Returns:
        str: Rendered string
    """
    if not template:
        return ""
    
    result = template
    for key, value in data.items():
        placeholder = f"{{{{{key}}}}}"
        result = result.replace(placeholder, str(value))
    
    return result


@celery_app.task
def check_all_triggers() -> Dict[str, Any]:
    """
    Periodic task to check all automation triggers.
    
    Scans for conditions that should trigger automations.
    
    Returns:
        dict: Check results
    """
    logger.info("Checking all automation triggers")
    
    import asyncio
    return asyncio.run(_check_all_triggers_async())


async def _check_all_triggers_async() -> Dict[str, Any]:
    """Async implementation of trigger checking."""
    
    triggered = []
    
    async with get_db_context() as db:
        # Get active automations
        result = await db.execute(
            select(AutomationRule).where(AutomationRule.is_active == True)
        )
        automations = result.scalars().all()
        
        for automation in automations:
            if automation.trigger_type.value == "low_stock":
                # Check low stock conditions
                threshold = automation.trigger_config.get("threshold", 10)
                
                low_stock_result = await db.execute(
                    select(Inventory, Product)
                    .join(Product, Inventory.product_id == Product.id)
                    .where(Product.is_deleted == False)
                    .where(Inventory.quantity_available <= threshold)
                )
                
                for inventory, product in low_stock_result.all():
                    # Queue automation execution
                    from workers.celery_app import celery_app
                    celery_app.send_task(
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
                        "product_sku": product.sku
                    })
    
    logger.info(f"Trigger check completed, {len(triggered)} automations triggered")
    
    return {
        "checked_at": datetime.utcnow().isoformat(),
        "automations_checked": len(automations),
        "triggered_count": len(triggered),
        "triggered": triggered
    }
