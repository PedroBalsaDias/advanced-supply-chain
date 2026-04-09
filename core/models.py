"""
SQLAlchemy database models for Supply Chain Automation Platform.

Defines all database entities with relationships, indexes, and constraints.
"""

from datetime import datetime
from enum import Enum as PyEnum
from typing import List, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import expression
import uuid

from core.database import Base


class ProductStatus(str, PyEnum):
    """Product lifecycle status."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    DISCONTINUED = "discontinued"
    DRAFT = "draft"


class InventoryMovementType(str, PyEnum):
    """Types of inventory movements."""
    INBOUND = "inbound"           # Stock received
    OUTBOUND = "outbound"         # Stock shipped
    ADJUSTMENT = "adjustment"     # Manual correction
    TRANSFER = "transfer"         # Between locations
    RETURN = "return"             # Customer return


class OrderStatus(str, PyEnum):
    """Order processing status."""
    PENDING = "pending"
    CONFIRMED = "confirmed"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    RETURNED = "returned"


class AutomationTriggerType(str, PyEnum):
    """Types of automation triggers."""
    LOW_STOCK = "low_stock"
    NEW_ORDER = "new_order"
    PRICE_CHANGE = "price_change"
    SCHEDULED = "scheduled"
    WEBHOOK = "webhook"


class AutomationActionType(str, PyEnum):
    """Types of automation actions."""
    CREATE_PURCHASE_ORDER = "create_purchase_order"
    SEND_EMAIL = "send_email"
    UPDATE_PRICE = "update_price"
    NOTIFY_SLACK = "notify_slack"
    CALL_WEBHOOK = "call_webhook"
    UPDATE_INVENTORY = "update_inventory"


class User(Base):
    """User account for system access."""
    
    __tablename__ = "users"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )
    
    # Relationships
    audit_logs: Mapped[List["AuditLog"]] = relationship("AuditLog", back_populates="user")


class Product(Base):
    """Product catalog with master data."""
    
    __tablename__ = "products"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    sku: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    brand: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    unit_cost: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    unit_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    weight_kg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    dimensions_cm: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # {"l": 10, "w": 5, "h": 3}
    barcode: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, unique=True)
    supplier_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    status: Mapped[ProductStatus] = mapped_column(
        Enum(ProductStatus),
        default=ProductStatus.ACTIVE,
        nullable=False
    )
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)  # Soft delete
    metadata: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # Flexible attributes
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )
    
    # Relationships
    inventory: Mapped["Inventory"] = relationship("Inventory", back_populates="product", uselist=False)
    order_items: Mapped[List["OrderItem"]] = relationship("OrderItem", back_populates="product")
    movements: Mapped[List["InventoryMovement"]] = relationship("InventoryMovement", back_populates="product")
    
    # Indexes for common queries
    __table_args__ = (
        Index("ix_products_status_category", "status", "category"),
        Index("ix_products_supplier", "supplier_id"),
    )


class Inventory(Base):
    """Current inventory levels per product."""
    
    __tablename__ = "inventory"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        unique=True,
        nullable=False
    )
    quantity_available: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    quantity_reserved: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # For orders
    quantity_on_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # Incoming
    reorder_point: Mapped[int] = mapped_column(Integer, default=10)
    reorder_quantity: Mapped[int] = mapped_column(Integer, default=100)
    location: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    warehouse_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    last_counted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )
    
    # Relationships
    product: Mapped[Product] = relationship("Product", back_populates="inventory")
    
    # Computed property
    @property
    def quantity_total(self) -> int:
        """Total physical quantity (available + reserved)."""
        return self.quantity_available + self.quantity_reserved
    
    @property
    def is_low_stock(self) -> bool:
        """Check if stock is below reorder point."""
        return self.quantity_available <= self.reorder_point
    
    __table_args__ = (
        Index("ix_inventory_low_stock", "quantity_available", "reorder_point"),
        Index("ix_inventory_warehouse", "warehouse_id", "location"),
    )


class InventoryMovement(Base):
    """Historical record of all inventory changes."""
    
    __tablename__ = "inventory_movements"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    movement_type: Mapped[InventoryMovementType] = mapped_column(
        Enum(InventoryMovementType),
        nullable=False
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)  # Positive or negative
    reference_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # "order", "adjustment"
    reference_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    performed_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    product: Mapped[Product] = relationship("Product", back_populates="movements")
    
    __table_args__ = (
        Index("ix_movements_product_date", "product_id", "created_at"),
        Index("ix_movements_type_date", "movement_type", "created_at"),
    )


class Order(Base):
    """Customer or purchase orders."""
    
    __tablename__ = "orders"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    order_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    external_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)  # Shopify, Amazon
    channel: Mapped[str] = mapped_column(String(50), default="direct")  # shopify, amazon, direct
    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus),
        default=OrderStatus.PENDING,
        nullable=False
    )
    customer_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    customer_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    shipping_address: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    total_amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="BRL")
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    shipped_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )
    
    # Relationships
    items: Mapped[List["OrderItem"]] = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index("ix_orders_status_channel", "status", "channel"),
        Index("ix_orders_created", "created_at"),
    )


class OrderItem(Base):
    """Individual line items within an order."""
    
    __tablename__ = "order_items"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False
    )
    product_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id"),
        nullable=True
    )
    sku: Mapped[str] = mapped_column(String(100), nullable=False)
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[float] = mapped_column(Float, nullable=False)
    total_price: Mapped[float] = mapped_column(Float, nullable=False)
    
    # Relationships
    order: Mapped[Order] = relationship("Order", back_populates="items")
    product: Mapped[Optional[Product]] = relationship("Product", back_populates="order_items")


class AutomationRule(Base):
    """User-defined automation rules (triggers and actions)."""
    
    __tablename__ = "automation_rules"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Trigger configuration
    trigger_type: Mapped[AutomationTriggerType] = mapped_column(Enum(AutomationTriggerType), nullable=False)
    trigger_config: Mapped[dict] = mapped_column(JSON, default=dict)  # e.g., {"threshold": 5, "product_category": "electronics"}
    
    # Action configuration
    action_type: Mapped[AutomationActionType] = mapped_column(Enum(AutomationActionType), nullable=False)
    action_config: Mapped[dict] = mapped_column(JSON, default=dict)  # e.g., {"email": "buyer@company.com", "quantity": 100}
    
    # Execution tracking
    last_triggered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    trigger_count: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )
    
    __table_args__ = (
        Index("ix_automations_active_trigger", "is_active", "trigger_type"),
    )


class AuditLog(Base):
    """Comprehensive audit trail for compliance."""
    
    __tablename__ = "audit_logs"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    table_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    record_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(50), nullable=False)  # CREATE, UPDATE, DELETE
    old_values: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    new_values: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    performed_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True
    )
    performed_by_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    
    # Relationships
    user: Mapped[Optional[User]] = relationship("User", back_populates="audit_logs")
    
    __table_args__ = (
        Index("ix_audit_logs_table_record", "table_name", "record_id"),
        Index("ix_audit_logs_created", "created_at"),
    )


class IntegrationSync(Base):
    """Track synchronization with external platforms."""
    
    __tablename__ = "integration_syncs"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    platform: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # shopify, amazon
    sync_type: Mapped[str] = mapped_column(String(50), nullable=False)  # products, orders, inventory
    status: Mapped[str] = mapped_column(String(50), nullable=False)  # running, completed, failed
    records_processed: Mapped[int] = mapped_column(Integer, default=0)
    records_created: Mapped[int] = mapped_column(Integer, default=0)
    records_updated: Mapped[int] = mapped_column(Integer, default=0)
    records_failed: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
