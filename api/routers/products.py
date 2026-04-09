"""
Products router with full CRUD operations.

Features:
- Complete CRUD with soft delete
- Pagination and filtering
- Search by name/SKU
- Category and brand filtering
"""

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.routers.auth import get_current_user
from core.database import get_db_session
from core.logging import get_logger
from core.models import Product, ProductStatus, User

logger = get_logger(__name__)
router = APIRouter()


# Pydantic Schemas
class ProductCreate(BaseModel):
    """Schema for creating a new product."""
    sku: str = Field(..., min_length=1, max_length=100, description="Unique stock keeping unit")
    name: str = Field(..., min_length=1, max_length=255, description="Product name")
    description: Optional[str] = Field(None, max_length=5000, description="Product description")
    category: Optional[str] = Field(None, max_length=100, description="Product category")
    brand: Optional[str] = Field(None, max_length=100, description="Brand name")
    unit_cost: Optional[float] = Field(None, ge=0, description="Unit cost in currency")
    unit_price: Optional[float] = Field(None, ge=0, description="Selling price in currency")
    weight_kg: Optional[float] = Field(None, ge=0, description="Weight in kilograms")
    dimensions_cm: Optional[dict] = Field(None, description="Dimensions {length, width, height}")
    barcode: Optional[str] = Field(None, max_length=50, description="Barcode/EAN")
    supplier_id: Optional[str] = Field(None, max_length=100, description="Supplier identifier")
    status: ProductStatus = Field(default=ProductStatus.ACTIVE, description="Product status")
    metadata: Optional[dict] = Field(None, description="Additional flexible attributes")


class ProductUpdate(BaseModel):
    """Schema for updating an existing product."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=5000)
    category: Optional[str] = Field(None, max_length=100)
    brand: Optional[str] = Field(None, max_length=100)
    unit_cost: Optional[float] = Field(None, ge=0)
    unit_price: Optional[float] = Field(None, ge=0)
    weight_kg: Optional[float] = Field(None, ge=0)
    dimensions_cm: Optional[dict] = None
    barcode: Optional[str] = Field(None, max_length=50)
    supplier_id: Optional[str] = Field(None, max_length=100)
    status: Optional[ProductStatus] = None
    metadata: Optional[dict] = None


class ProductResponse(BaseModel):
    """Schema for product response."""
    id: UUID
    sku: str
    name: str
    description: Optional[str]
    category: Optional[str]
    brand: Optional[str]
    unit_cost: Optional[float]
    unit_price: Optional[float]
    weight_kg: Optional[float]
    dimensions_cm: Optional[dict]
    barcode: Optional[str]
    supplier_id: Optional[str]
    status: ProductStatus
    is_deleted: bool
    metadata: Optional[dict]
    created_at: str
    updated_at: str
    
    class Config:
        from_attributes = True


class ProductListResponse(BaseModel):
    """Paginated product list response."""
    items: List[ProductResponse]
    total: int
    page: int
    page_size: int
    pages: int


class ProductFilterParams(BaseModel):
    """Query parameters for filtering products."""
    search: Optional[str] = None
    category: Optional[str] = None
    brand: Optional[str] = None
    status: Optional[ProductStatus] = None
    supplier_id: Optional[str] = None
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    include_deleted: bool = False


# Endpoints
@router.post("", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
async def create_product(
    product_data: ProductCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user)
) -> Product:
    """
    Create a new product in the catalog.
    
    Args:
        product_data: Product creation data
        db: Database session
        current_user: Authenticated user
        
    Returns:
        Product: Created product
        
    Raises:
        HTTPException: If SKU already exists
    """
    # Check for duplicate SKU
    existing = await db.execute(
        select(Product).where(Product.sku == product_data.sku, Product.is_deleted == False)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Product with SKU '{product_data.sku}' already exists"
        )
    
    # Create product
    product = Product(**product_data.model_dump())
    db.add(product)
    await db.commit()
    await db.refresh(product)
    
    logger.info("Product created", product_id=str(product.id), sku=product.sku)
    
    return product


@router.get("", response_model=ProductListResponse)
async def list_products(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    sort_by: str = Query("created_at", regex="^(name|sku|created_at|updated_at|unit_price)$"),
    sort_order: str = Query("desc", regex="^(asc|desc)$"),
    search: Optional[str] = None,
    category: Optional[str] = None,
    brand: Optional[str] = None,
    status: Optional[ProductStatus] = None,
    supplier_id: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    include_deleted: bool = False,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user)
) -> dict:
    """
    List products with filtering and pagination.
    
    Args:
        page: Page number (1-indexed)
        page_size: Items per page
        sort_by: Sort field
        sort_order: Sort direction
        search: Search in name and SKU
        category: Filter by category
        brand: Filter by brand
        status: Filter by status
        supplier_id: Filter by supplier
        min_price: Minimum price filter
        max_price: Maximum price filter
        include_deleted: Include soft-deleted products
        db: Database session
        current_user: Authenticated user
        
    Returns:
        dict: Paginated product list
    """
    # Build query
    query = select(Product)
    filters = []
    
    # Soft delete filter
    if not include_deleted:
        filters.append(Product.is_deleted == False)
    
    # Search in name and SKU
    if search:
        search_filter = or_(
            Product.name.ilike(f"%{search}%"),
            Product.sku.ilike(f"%{search}%"),
            Product.barcode.ilike(f"%{search}%") if Product.barcode is not None else False
        )
        filters.append(search_filter)
    
    # Category filter
    if category:
        filters.append(Product.category == category)
    
    # Brand filter
    if brand:
        filters.append(Product.brand == brand)
    
    # Status filter
    if status:
        filters.append(Product.status == status)
    
    # Supplier filter
    if supplier_id:
        filters.append(Product.supplier_id == supplier_id)
    
    # Price range filters
    if min_price is not None:
        filters.append(Product.unit_price >= min_price)
    if max_price is not None:
        filters.append(Product.unit_price <= max_price)
    
    # Apply filters
    if filters:
        query = query.where(and_(*filters))
    
    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()
    
    # Sorting
    sort_column = getattr(Product, sort_by)
    if sort_order == "desc":
        sort_column = sort_column.desc()
    query = query.order_by(sort_column)
    
    # Pagination
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)
    
    # Execute
    result = await db.execute(query)
    products = result.scalars().all()
    
    pages = (total + page_size - 1) // page_size
    
    return {
        "items": products,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": pages
    }


@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(
    product_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user)
) -> Product:
    """
    Get a single product by ID.
    
    Args:
        product_id: Product UUID
        db: Database session
        current_user: Authenticated user
        
    Returns:
        Product: Product details
        
    Raises:
        HTTPException: If product not found
    """
    result = await db.execute(
        select(Product).where(Product.id == product_id, Product.is_deleted == False)
    )
    product = result.scalar_one_or_none()
    
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with ID '{product_id}' not found"
        )
    
    return product


@router.put("/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: UUID,
    product_data: ProductUpdate,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user)
) -> Product:
    """
    Update an existing product.
    
    Args:
        product_id: Product UUID
        product_data: Update data
        db: Database session
        current_user: Authenticated user
        
    Returns:
        Product: Updated product
        
    Raises:
        HTTPException: If product not found
    """
    result = await db.execute(
        select(Product).where(Product.id == product_id, Product.is_deleted == False)
    )
    product = result.scalar_one_or_none()
    
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with ID '{product_id}' not found"
        )
    
    # Update only provided fields
    update_data = product_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(product, field, value)
    
    await db.commit()
    await db.refresh(product)
    
    logger.info("Product updated", product_id=str(product_id), updated_fields=list(update_data.keys()))
    
    return product


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(
    product_id: UUID,
    permanent: bool = Query(False, description="Permanently delete instead of soft delete"),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user)
) -> None:
    """
    Delete a product (soft delete by default).
    
    Args:
        product_id: Product UUID
        permanent: If True, permanently delete from database
        db: Database session
        current_user: Authenticated user
        
    Raises:
        HTTPException: If product not found
    """
    result = await db.execute(
        select(Product).where(Product.id == product_id, Product.is_deleted == False)
    )
    product = result.scalar_one_or_none()
    
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with ID '{product_id}' not found"
        )
    
    if permanent:
        await db.delete(product)
        logger.info("Product permanently deleted", product_id=str(product_id))
    else:
        product.is_deleted = True
        product.status = ProductStatus.INACTIVE
        logger.info("Product soft deleted", product_id=str(product_id))
    
    await db.commit()


@router.post("/{product_id}/restore", response_model=ProductResponse)
async def restore_product(
    product_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user)
) -> Product:
    """
    Restore a soft-deleted product.
    
    Args:
        product_id: Product UUID
        db: Database session
        current_user: Authenticated user
        
    Returns:
        Product: Restored product
        
    Raises:
        HTTPException: If product not found or not deleted
    """
    result = await db.execute(
        select(Product).where(Product.id == product_id, Product.is_deleted == True)
    )
    product = result.scalar_one_or_none()
    
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Deleted product with ID '{product_id}' not found"
        )
    
    product.is_deleted = False
    product.status = ProductStatus.ACTIVE
    await db.commit()
    await db.refresh(product)
    
    logger.info("Product restored", product_id=str(product_id))
    
    return product


@router.get("/categories/list", response_model=List[str])
async def list_categories(
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user)
) -> List[str]:
    """
    Get all unique product categories.
    
    Args:
        db: Database session
        current_user: Authenticated user
        
    Returns:
        List[str]: Unique categories
    """
    result = await db.execute(
        select(Product.category)
        .where(Product.is_deleted == False)
        .where(Product.category.isnot(None))
        .distinct()
        .order_by(Product.category)
    )
    categories = [row[0] for row in result.all() if row[0]]
    return categories


@router.get("/brands/list", response_model=List[str])
async def list_brands(
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user)
) -> List[str]:
    """
    Get all unique product brands.
    
    Args:
        db: Database session
        current_user: Authenticated user
        
    Returns:
        List[str]: Unique brands
    """
    result = await db.execute(
        select(Product.brand)
        .where(Product.is_deleted == False)
        .where(Product.brand.isnot(None))
        .distinct()
        .order_by(Product.brand)
    )
    brands = [row[0] for row in result.all() if row[0]]
    return brands
