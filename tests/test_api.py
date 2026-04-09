"""
API endpoint tests.

Tests for all API routers including authentication, products,
inventory, orders, and automations.
"""

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient

from core.models import User


# Health Check Tests
class TestHealth:
    """Test health check endpoints."""
    
    def test_health_check(self, client: TestClient) -> None:
        """Test health endpoint returns healthy status."""
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data
    
    def test_root_endpoint(self, client: TestClient) -> None:
        """Test root endpoint returns API info."""
        response = client.get("/")
        
        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "docs" in data


# Authentication Tests
class TestAuthentication:
    """Test authentication endpoints."""
    
    def test_login_success(self, client: TestClient, test_user: User) -> None:
        """Test successful login returns tokens."""
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "test@example.com", "password": "testpassword"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
    
    def test_login_invalid_credentials(self, client: TestClient) -> None:
        """Test login with invalid credentials fails."""
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "test@example.com", "password": "wrongpassword"}
        )
        
        assert response.status_code == 401
        assert "detail" in response.json()
    
    def test_get_current_user(self, client: TestClient, auth_headers: dict) -> None:
        """Test getting current user with valid token."""
        response = client.get("/api/v1/auth/me", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "test@example.com"
        assert data["full_name"] == "Test User"
    
    def test_get_current_user_no_token(self, client: TestClient) -> None:
        """Test accessing protected endpoint without token fails."""
        response = client.get("/api/v1/auth/me")
        
        assert response.status_code == 403


# Product Tests
class TestProducts:
    """Test product endpoints."""
    
    def test_create_product(self, client: TestClient, auth_headers: dict) -> None:
        """Test creating a new product."""
        product_data = {
            "sku": "TEST-001",
            "name": "Test Product",
            "description": "A test product",
            "category": "Electronics",
            "brand": "TestBrand",
            "unit_cost": 50.00,
            "unit_price": 99.99,
            "status": "active"
        }
        
        response = client.post(
            "/api/v1/products",
            json=product_data,
            headers=auth_headers
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["sku"] == "TEST-001"
        assert data["name"] == "Test Product"
        assert "id" in data
    
    def test_create_product_duplicate_sku(self, client: TestClient, auth_headers: dict) -> None:
        """Test creating product with duplicate SKU fails."""
        product_data = {
            "sku": "DUPLICATE-001",
            "name": "First Product",
            "status": "active"
        }
        
        # Create first product
        client.post("/api/v1/products", json=product_data, headers=auth_headers)
        
        # Try to create second with same SKU
        product_data["name"] = "Second Product"
        response = client.post(
            "/api/v1/products",
            json=product_data,
            headers=auth_headers
        )
        
        assert response.status_code == 409
    
    def test_list_products(self, client: TestClient, auth_headers: dict) -> None:
        """Test listing products with pagination."""
        response = client.get("/api/v1/products", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert isinstance(data["items"], list)
    
    def test_list_products_with_filters(self, client: TestClient, auth_headers: dict) -> None:
        """Test listing products with filters."""
        response = client.get(
            "/api/v1/products?category=Electronics&status=active",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
    
    def test_get_product(self, client: TestClient, auth_headers: dict) -> None:
        """Test getting a single product."""
        # Create product first
        product_data = {
            "sku": "GET-001",
            "name": "Get Test Product",
            "status": "active"
        }
        create_response = client.post(
            "/api/v1/products",
            json=product_data,
            headers=auth_headers
        )
        product_id = create_response.json()["id"]
        
        # Get product
        response = client.get(f"/api/v1/products/{product_id}", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["sku"] == "GET-001"
        assert data["name"] == "Get Test Product"
    
    def test_get_product_not_found(self, client: TestClient, auth_headers: dict) -> None:
        """Test getting non-existent product returns 404."""
        response = client.get(
            "/api/v1/products/12345678-1234-1234-1234-123456789abc",
            headers=auth_headers
        )
        
        assert response.status_code == 404
    
    def test_update_product(self, client: TestClient, auth_headers: dict) -> None:
        """Test updating a product."""
        # Create product
        product_data = {
            "sku": "UPDATE-001",
            "name": "Original Name",
            "status": "active"
        }
        create_response = client.post(
            "/api/v1/products",
            json=product_data,
            headers=auth_headers
        )
        product_id = create_response.json()["id"]
        
        # Update product
        update_data = {"name": "Updated Name", "unit_price": 149.99}
        response = client.put(
            f"/api/v1/products/{product_id}",
            json=update_data,
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Name"
        assert data["unit_price"] == 149.99
    
    def test_delete_product_soft(self, client: TestClient, auth_headers: dict) -> None:
        """Test soft deleting a product."""
        # Create product
        product_data = {
            "sku": "DELETE-001",
            "name": "Delete Test Product",
            "status": "active"
        }
        create_response = client.post(
            "/api/v1/products",
            json=product_data,
            headers=auth_headers
        )
        product_id = create_response.json()["id"]
        
        # Soft delete
        response = client.delete(
            f"/api/v1/products/{product_id}",
            headers=auth_headers
        )
        
        assert response.status_code == 204
        
        # Verify product is soft deleted (not found in normal list)
        get_response = client.get(
            f"/api/v1/products/{product_id}",
            headers=auth_headers
        )
        assert get_response.status_code == 404


# Inventory Tests
class TestInventory:
    """Test inventory endpoints."""
    
    def test_get_inventory_levels(self, client: TestClient, auth_headers: dict) -> None:
        """Test getting inventory levels."""
        response = client.get("/api/v1/inventory/levels", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    def test_update_stock(self, client: TestClient, auth_headers: dict) -> None:
        """Test updating stock quantity."""
        # Create product first
        product_data = {
            "sku": "STOCK-001",
            "name": "Stock Test Product",
            "status": "active"
        }
        create_response = client.post(
            "/api/v1/products",
            json=product_data,
            headers=auth_headers
        )
        product_id = create_response.json()["id"]
        
        # Add stock
        update_data = {
            "quantity_change": 100,
            "movement_type": "inbound",
            "notes": "Initial stock"
        }
        response = client.post(
            f"/api/v1/inventory/update/{product_id}",
            json=update_data,
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["quantity_available"] == 100
    
    def test_get_low_stock_alerts(self, client: TestClient, auth_headers: dict) -> None:
        """Test getting low stock alerts."""
        response = client.get("/api/v1/inventory/alerts/low-stock", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    def test_get_inventory_summary(self, client: TestClient, auth_headers: dict) -> None:
        """Test getting inventory summary."""
        response = client.get("/api/v1/inventory/dashboard/summary", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert "total_products" in data
        assert "total_units" in data


# Order Tests
class TestOrders:
    """Test order endpoints."""
    
    def test_create_order(self, client: TestClient, auth_headers: dict) -> None:
        """Test creating a new order."""
        order_data = {
            "channel": "direct",
            "customer_email": "customer@example.com",
            "customer_name": "John Doe",
            "items": [
                {
                    "sku": "ORDER-ITEM-001",
                    "product_name": "Order Test Item",
                    "quantity": 2,
                    "unit_price": 29.99
                }
            ]
        }
        
        response = client.post(
            "/api/v1/orders",
            json=order_data,
            headers=auth_headers
        )
        
        assert response.status_code == 201
        data = response.json()
        assert "order_number" in data
        assert data["status"] == "pending"
        assert len(data["items"]) == 1
    
    def test_list_orders(self, client: TestClient, auth_headers: dict) -> None:
        """Test listing orders."""
        response = client.get("/api/v1/orders", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
    
    def test_get_order(self, client: TestClient, auth_headers: dict) -> None:
        """Test getting a single order."""
        # Create order first
        order_data = {
            "channel": "direct",
            "items": [
                {
                    "sku": "GET-ORDER-001",
                    "product_name": "Get Order Item",
                    "quantity": 1,
                    "unit_price": 49.99
                }
            ]
        }
        create_response = client.post(
            "/api/v1/orders",
            json=order_data,
            headers=auth_headers
        )
        order_id = create_response.json()["id"]
        
        # Get order
        response = client.get(f"/api/v1/orders/{order_id}", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["items"][0]["sku"] == "GET-ORDER-001"
    
    def test_update_order_status(self, client: TestClient, auth_headers: dict) -> None:
        """Test updating order status."""
        # Create order
        order_data = {
            "channel": "direct",
            "items": [
                {
                    "sku": "STATUS-001",
                    "product_name": "Status Test Item",
                    "quantity": 1,
                    "unit_price": 99.99
                }
            ]
        }
        create_response = client.post(
            "/api/v1/orders",
            json=order_data,
            headers=auth_headers
        )
        order_id = create_response.json()["id"]
        
        # Update status
        response = client.patch(
            f"/api/v1/orders/{order_id}/status",
            json={"status": "confirmed"},
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "confirmed"


# Automation Tests
class TestAutomations:
    """Test automation endpoints."""
    
    def test_create_automation(self, client: TestClient, auth_headers: dict) -> None:
        """Test creating an automation rule."""
        automation_data = {
            "name": "Low Stock Alert Test",
            "description": "Test automation for low stock",
            "is_active": True,
            "trigger_type": "low_stock",
            "trigger_config": {"threshold": 10},
            "action_type": "send_email",
            "action_config": {
                "email_to": "admin@example.com",
                "email_subject": "Stock Alert"
            }
        }
        
        response = client.post(
            "/api/v1/automations",
            json=automation_data,
            headers=auth_headers
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Low Stock Alert Test"
        assert data["trigger_type"] == "low_stock"
    
    def test_list_automations(self, client: TestClient, auth_headers: dict) -> None:
        """Test listing automation rules."""
        response = client.get("/api/v1/automations", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    def test_get_automation_templates(self, client: TestClient, auth_headers: dict) -> None:
        """Test getting automation templates."""
        response = client.get("/api/v1/automations/templates/available", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0


# Async Tests Example
@pytest.mark.asyncio
async def test_async_health_check(async_client: AsyncClient) -> None:
    """Test health check with async client."""
    response = await async_client.get("/health")
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
