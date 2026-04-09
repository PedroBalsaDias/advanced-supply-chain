"""
Celery worker tests.

Tests for background task processing.
"""

from unittest.mock import MagicMock, patch

import pytest

from workers.tasks.sync import (
    sync_shopify_products,
    sync_shopify_inventory,
    sync_amazon_orders,
)
from workers.tasks.automation_engine import execute_automation


class TestSyncTasks:
    """Test synchronization tasks."""
    
    def test_sync_shopify_products(self) -> None:
        """Test Shopify product sync task."""
        # Mock the task
        with patch("workers.tasks.sync.logger") as mock_logger:
            result = sync_shopify_products()
        
        assert result["status"] == "success"
        assert result["platform"] == "shopify"
        assert result["sync_type"] == "products"
        assert "records_processed" in result
    
    def test_sync_shopify_inventory(self) -> None:
        """Test Shopify inventory sync task."""
        result = sync_shopify_inventory()
        
        assert result["platform"] == "shopify"
        assert result["sync_type"] == "inventory"
        assert result["status"] == "success"
    
    def test_sync_amazon_orders(self) -> None:
        """Test Amazon order sync task."""
        result = sync_amazon_orders(since_hours=24)
        
        assert result["platform"] == "amazon"
        assert result["sync_type"] == "orders"
        assert result["status"] == "success"
    
    def test_sync_task_retry_on_failure(self) -> None:
        """Test that sync tasks retry on failure."""
        # This would test the retry mechanism
        # In practice, you'd mock an exception and verify retry
        pass


class TestAutomationTasks:
    """Test automation engine tasks."""
    
    @patch("workers.tasks.automation_engine.get_db_context")
    async def test_execute_automation_email_action(self, mock_db_context) -> None:
        """Test executing email automation action."""
        # Setup mock
        mock_db = MagicMock()
        mock_db_context.return_value.__aenter__ = MagicMock(return_value=mock_db)
        mock_db_context.return_value.__aexit__ = MagicMock(return_value=None)
        
        # Mock automation rule
        mock_automation = MagicMock()
        mock_automation.id = "123e4567-e89b-12d3-a456-426614174000"
        mock_automation.name = "Test Automation"
        mock_automation.is_active = True
        mock_automation.trigger_type.value = "low_stock"
        mock_automation.action_type.value = "send_email"
        mock_automation.action_config = {
            "email_to": "test@example.com",
            "email_subject": "Test Alert"
        }
        mock_automation.trigger_count = 0
        
        # Execute (would need proper async mocking)
        # result = await execute_automation("123", {"sku": "TEST-001", "quantity": 5})
        pass
    
    def test_execute_automation_inactive(self) -> None:
        """Test that inactive automations are skipped."""
        # Would test that inactive automations return skipped status
        pass


class TestCeleryConfiguration:
    """Test Celery configuration."""
    
    def test_celery_app_exists(self) -> None:
        """Test that Celery app is properly configured."""
        from workers.celery_app import celery_app
        
        assert celery_app is not None
        assert celery_app.main == "supply_chain"
    
    def test_celery_beat_schedule(self) -> None:
        """Test Celery beat schedule configuration."""
        from workers.celery_app import celery_app
        
        beat_schedule = celery_app.conf.beat_schedule
        
        assert "sync-shopify-inventory" in beat_schedule
        assert "sync-amazon-orders" in beat_schedule
        assert "check-automation-triggers" in beat_schedule
