"""
Database seeding script.

Populates the database with sample data for testing and demonstration.
"""

import asyncio
import uuid
from datetime import datetime

from sqlalchemy import select

from core.database import get_db_context, init_database
from core.logging import configure_logging, get_logger
from core.models import (
    AutomationActionType,
    AutomationRule,
    AutomationTriggerType,
    Inventory,
    InventoryMovement,
    InventoryMovementType,
    Order,
    OrderItem,
    OrderStatus,
    Product,
    ProductStatus,
    User,
)

configure_logging()
logger = get_logger(__name__)


async def seed_users(db) -> None:
    """Create sample users."""
    logger.info("Seeding users...")
    
    # Check if users already exist
    result = await db.execute(select(User).where(User.email == "admin@supplychain.com"))
    if result.scalar_one_or_none():
        logger.info("Users already seeded, skipping...")
        return
    
    from api.routers.auth import get_password_hash
    
    admin_user = User(
        id=uuid.uuid4(),
        email="admin@supplychain.com",
        hashed_password=get_password_hash("admin123"),
        full_name="Administrator",
        is_active=True,
        is_superuser=True
    )
    
    manager_user = User(
        id=uuid.uuid4(),
        email="manager@supplychain.com",
        hashed_password=get_password_hash("manager123"),
        full_name="Supply Chain Manager",
        is_active=True,
        is_superuser=False
    )
    
    db.add_all([admin_user, manager_user])
    await db.commit()
    logger.info("Users seeded successfully")


async def seed_products(db) -> None:
    """Create sample products."""
    logger.info("Seeding products...")
    
    # Check if products already exist
    result = await db.execute(select(Product).limit(1))
    if result.scalar_one_or_none():
        logger.info("Products already seeded, skipping...")
        return
    
    products = [
        Product(
            id=uuid.uuid4(),
            sku="ELEC-PHONE-001",
            name="Wireless Bluetooth Headphones",
            description="Premium noise-cancelling wireless headphones with 30-hour battery life",
            category="Electronics",
            brand="AudioTech",
            unit_cost=45.00,
            unit_price=89.99,
            weight_kg=0.3,
            dimensions_cm={"length": 20, "width": 18, "height": 8},
            barcode="1234567890123",
            supplier_id="SUP-001",
            status=ProductStatus.ACTIVE,
            metadata={"color": "black", "warranty_months": 24}
        ),
        Product(
            id=uuid.uuid4(),
            sku="ELEC-CHRG-001",
            name="USB-C Fast Charging Cable",
            description="2m braided USB-C to USB-C cable, 100W fast charging support",
            category="Electronics",
            brand="CableCo",
            unit_cost=5.00,
            unit_price=12.99,
            weight_kg=0.1,
            dimensions_cm={"length": 200, "width": 2, "height": 2},
            barcode="1234567890124",
            supplier_id="SUP-002",
            status=ProductStatus.ACTIVE,
            metadata={"length_m": 2, "color": "gray"}
        ),
        Product(
            id=uuid.uuid4(),
            sku="HOME-LAMP-001",
            name="Smart LED Desk Lamp",
            description="Dimmable LED desk lamp with wireless charging base and app control",
            category="Home & Office",
            brand="LumiSmart",
            unit_cost=25.00,
            unit_price=49.99,
            weight_kg=0.8,
            dimensions_cm={"length": 15, "width": 15, "height": 45},
            barcode="1234567890125",
            supplier_id="SUP-003",
            status=ProductStatus.ACTIVE,
            metadata={"color_temp": "2700K-6500K", "wireless_charging": True}
        ),
        Product(
            id=uuid.uuid4(),
            sku="SPORT-BOTTLE-001",
            name="Insulated Water Bottle 750ml",
            description="Double-wall vacuum insulated stainless steel bottle",
            category="Sports & Outdoors",
            brand="HydroLife",
            unit_cost=8.00,
            unit_price=19.99,
            weight_kg=0.4,
            dimensions_cm={"length": 8, "width": 8, "height": 28},
            barcode="1234567890126",
            supplier_id="SUP-004",
            status=ProductStatus.ACTIVE,
            metadata={"capacity_ml": 750, "color": "blue"}
        ),
        Product(
            id=uuid.uuid4(),
            sku="ELEC-PHONE-002",
            name="Wireless Earbuds Pro",
            description="True wireless earbuds with active noise cancellation",
            category="Electronics",
            brand="AudioTech",
            unit_cost=60.00,
            unit_price=129.99,
            weight_kg=0.05,
            dimensions_cm={"length": 6, "width": 4, "height": 3},
            barcode="1234567890127",
            supplier_id="SUP-001",
            status=ProductStatus.ACTIVE,
            metadata={"battery_hours": 8, "color": "white"}
        ),
        Product(
            id=uuid.uuid4(),
            sku="OFFICE-CHAIR-001",
            name="Ergonomic Office Chair",
            description="Adjustable ergonomic chair with lumbar support",
            category="Home & Office",
            brand="ComfortSeat",
            unit_cost=150.00,
            unit_price=299.99,
            weight_kg=18.0,
            dimensions_cm={"length": 70, "width": 70, "height": 110},
            barcode="1234567890128",
            supplier_id="SUP-005",
            status=ProductStatus.ACTIVE,
            metadata={"max_weight_kg": 150, "warranty_years": 5}
        ),
        # Low stock product for testing
        Product(
            id=uuid.uuid4(),
            sku="ELEC-ADAPT-001",
            name="Universal Travel Adapter",
            description="All-in-one international travel adapter with USB ports",
            category="Electronics",
            brand="TravelTech",
            unit_cost=12.00,
            unit_price=24.99,
            weight_kg=0.2,
            dimensions_cm={"length": 7, "width": 5, "height": 6},
            barcode="1234567890129",
            supplier_id="SUP-002",
            status=ProductStatus.ACTIVE,
            metadata={"plugs": ["US", "EU", "UK", "AU"]}
        ),
        # Discontinued product
        Product(
            id=uuid.uuid4(),
            sku="ELEC-OLD-001",
            name="Wired Mouse (Old Model)",
            description="Basic wired USB mouse - discontinued",
            category="Electronics",
            brand="TechGear",
            unit_cost=5.00,
            unit_price=0,
            status=ProductStatus.DISCONTINUED,
            is_deleted=True
        ),
    ]
    
    for product in products:
        db.add(product)
    
    await db.commit()
    logger.info(f"Seeded {len(products)} products")


async def seed_inventory(db) -> None:
    """Create inventory records for products."""
    logger.info("Seeding inventory...")
    
    # Check if inventory already exists
    result = await db.execute(select(Inventory).limit(1))
    if result.scalar_one_or_none():
        logger.info("Inventory already seeded, skipping...")
        return
    
    # Get all active products
    result = await db.execute(
        select(Product).where(Product.is_deleted == False).where(Product.status == ProductStatus.ACTIVE)
    )
    products = result.scalars().all()
    
    inventory_data = {
        "ELEC-PHONE-001": (45, 5, 50),  # available, reserved, reorder_point
        "ELEC-CHRG-001": (120, 0, 50),
        "HOME-LAMP-001": (25, 2, 15),
        "SPORT-BOTTLE-001": (8, 0, 20),  # Low stock
        "ELEC-PHONE-002": (30, 3, 25),
        "OFFICE-CHAIR-001": (12, 1, 5),
        "ELEC-ADAPT-001": (3, 0, 10),   # Critical low stock
    }
    
    for product in products:
        if product.sku in inventory_data:
            available, reserved, reorder = inventory_data[product.sku]
            inventory = Inventory(
                id=uuid.uuid4(),
                product_id=product.id,
                quantity_available=available,
                quantity_reserved=reserved,
                quantity_on_order=0,
                reorder_point=reorder,
                reorder_quantity=reorder * 3,
                location="Warehouse-A",
                warehouse_id="WH-001"
            )
            db.add(inventory)
            
            # Create initial movement record
            movement = InventoryMovement(
                id=uuid.uuid4(),
                product_id=product.id,
                movement_type=InventoryMovementType.INBOUND,
                quantity=available + reserved,
                reference_type="initial_stock",
                reference_id="SEED",
                notes="Initial inventory seeding",
                performed_by="system"
            )
            db.add(movement)
    
    await db.commit()
    logger.info(f"Seeded inventory for {len(inventory_data)} products")


async def seed_orders(db) -> None:
    """Create sample orders."""
    logger.info("Seeding orders...")
    
    # Check if orders already exist
    result = await db.execute(select(Order).limit(1))
    if result.scalar_one_or_none():
        logger.info("Orders already seeded, skipping...")
        return
    
    # Get products
    result = await db.execute(
        select(Product).where(Product.sku.in_(["ELEC-PHONE-001", "ELEC-CHRG-001", "HOME-LAMP-001"]))
    )
    products = {p.sku: p for p in result.scalars().all()}
    
    if len(products) < 3:
        logger.warning("Not enough products found for order seeding")
        return
    
    orders = [
        Order(
            id=uuid.uuid4(),
            order_number="SC-20240401-0001",
            channel="shopify",
            status=OrderStatus.DELIVERED,
            customer_email="john.doe@example.com",
            customer_name="John Doe",
            shipping_address={
                "street": "123 Main St",
                "city": "Sao Paulo",
                "state": "SP",
                "zip": "01000-000",
                "country": "BR"
            },
            total_amount=102.98,
            currency="BRL",
            notes="Gift wrap requested"
        ),
        Order(
            id=uuid.uuid4(),
            order_number="SC-20240401-0002",
            channel="amazon",
            status=OrderStatus.SHIPPED,
            customer_email="jane.smith@example.com",
            customer_name="Jane Smith",
            shipping_address={
                "street": "456 Oak Ave",
                "city": "Rio de Janeiro",
                "state": "RJ",
                "zip": "20000-000",
                "country": "BR"
            },
            total_amount=89.99,
            currency="BRL"
        ),
        Order(
            id=uuid.uuid4(),
            order_number="SC-20240402-0001",
            channel="direct",
            status=OrderStatus.PROCESSING,
            customer_email="bob.wilson@example.com",
            customer_name="Bob Wilson",
            shipping_address={
                "street": "789 Pine Rd",
                "city": "Belo Horizonte",
                "state": "MG",
                "zip": "30000-000",
                "country": "BR"
            },
            total_amount=62.98,
            currency="BRL"
        ),
        Order(
            id=uuid.uuid4(),
            order_number="SC-20240402-0002",
            channel="shopify",
            status=OrderStatus.PENDING,
            customer_email="alice.jones@example.com",
            customer_name="Alice Jones",
            shipping_address={
                "street": "321 Elm St",
                "city": "Curitiba",
                "state": "PR",
                "zip": "80000-000",
                "country": "BR"
            },
            total_amount=349.98,
            currency="BRL"
        ),
    ]
    
    # Add order items
    orders[0].items = [
        OrderItem(
            id=uuid.uuid4(),
            product_id=products["ELEC-PHONE-001"].id,
            sku="ELEC-PHONE-001",
            product_name=products["ELEC-PHONE-001"].name,
            quantity=1,
            unit_price=89.99,
            total_price=89.99
        ),
        OrderItem(
            id=uuid.uuid4(),
            product_id=products["ELEC-CHRG-001"].id,
            sku="ELEC-CHRG-001",
            product_name=products["ELEC-CHRG-001"].name,
            quantity=1,
            unit_price=12.99,
            total_price=12.99
        )
    ]
    
    orders[1].items = [
        OrderItem(
            id=uuid.uuid4(),
            product_id=products["ELEC-PHONE-001"].id,
            sku="ELEC-PHONE-001",
            product_name=products["ELEC-PHONE-001"].name,
            quantity=1,
            unit_price=89.99,
            total_price=89.99
        )
    ]
    
    orders[2].items = [
        OrderItem(
            id=uuid.uuid4(),
            product_id=products["ELEC-CHRG-001"].id,
            sku="ELEC-CHRG-001",
            product_name=products["ELEC-CHRG-001"].name,
            quantity=2,
            unit_price=12.99,
            total_price=25.98
        ),
        OrderItem(
            id=uuid.uuid4(),
            product_id=products["HOME-LAMP-001"].id,
            sku="HOME-LAMP-001",
            product_name=products["HOME-LAMP-001"].name,
            quantity=1,
            unit_price=37.00,
            total_price=37.00
        )
    ]
    
    orders[3].items = [
        OrderItem(
            id=uuid.uuid4(),
            product_id=products["HOME-LAMP-001"].id,
            sku="HOME-LAMP-001",
            product_name=products["HOME-LAMP-001"].name,
            quantity=2,
            unit_price=49.99,
            total_price=99.98
        ),
        OrderItem(
            id=uuid.uuid4(),
            product_id=products["ELEC-PHONE-001"].id,
            sku="ELEC-PHONE-001",
            product_name=products["ELEC-PHONE-001"].name,
            quantity=1,
            unit_price=89.99,
            total_price=89.99
        ),
        OrderItem(
            id=uuid.uuid4(),
            product_id=products["ELEC-CHRG-001"].id,
            sku="ELEC-CHRG-001",
            product_name=products["ELEC-CHRG-001"].name,
            quantity=2,
            unit_price=12.99,
            total_price=25.99
        )
    ]
    
    for order in orders:
        db.add(order)
    
    await db.commit()
    logger.info(f"Seeded {len(orders)} orders")


async def seed_automations(db) -> None:
    """Create sample automation rules."""
    logger.info("Seeding automations...")
    
    # Check if automations already exist
    result = await db.execute(select(AutomationRule).limit(1))
    if result.scalar_one_or_none():
        logger.info("Automations already seeded, skipping...")
        return
    
    automations = [
        AutomationRule(
            id=uuid.uuid4(),
            name="Low Stock Email Alert",
            description="Send email when inventory falls below reorder point",
            is_active=True,
            trigger_type=AutomationTriggerType.LOW_STOCK,
            trigger_config={"threshold": 10},
            action_type=AutomationActionType.SEND_EMAIL,
            action_config={
                "email_to": "manager@supplychain.com",
                "email_subject": "Low Stock Alert: {{sku}}",
                "email_template": "Product {{name}} ({{sku}}) has only {{quantity}} units remaining."
            },
            created_by="system"
        ),
        AutomationRule(
            id=uuid.uuid4(),
            name="Auto Reorder Critical Items",
            description="Create purchase order for items with critical stock levels",
            is_active=True,
            trigger_type=AutomationTriggerType.LOW_STOCK,
            trigger_config={"threshold": 5},
            action_type=AutomationActionType.CREATE_PURCHASE_ORDER,
            action_config={
                "quantity_multiplier": 3,
                "supplier_email": "orders@supplier.com"
            },
            created_by="system"
        ),
        AutomationRule(
            id=uuid.uuid4(),
            name="New Order Slack Notification",
            description="Notify team on Slack when new order is received",
            is_active=True,
            trigger_type=AutomationTriggerType.NEW_ORDER,
            trigger_config={},
            action_type=AutomationActionType.NOTIFY_SLACK,
            action_config={
                "slack_channel": "#orders",
                "slack_message": "New order: {{order_number}} - ${{total_amount}}"
            },
            created_by="system"
        ),
    ]
    
    for automation in automations:
        db.add(automation)
    
    await db.commit()
    logger.info(f"Seeded {len(automations)} automation rules")


async def main():
    """Main seeding function."""
    logger.info("Starting database seeding...")
    
    async with get_db_context() as db:
        await seed_users(db)
        await seed_products(db)
        await seed_inventory(db)
        await seed_orders(db)
        await seed_automations(db)
    
    logger.info("Database seeding completed successfully!")
    logger.info("")
    logger.info("Sample login credentials:")
    logger.info("  Email: admin@supplychain.com")
    logger.info("  Password: admin123")
    logger.info("")
    logger.info("  Email: manager@supplychain.com")
    logger.info("  Password: manager123")


if __name__ == "__main__":
    asyncio.run(main())
