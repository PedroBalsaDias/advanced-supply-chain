"""
FastAPI application main entry point.

Provides:
- Lifespan management (startup/shutdown)
- JWT authentication
- API routing
- Middleware (logging, CORS, error handling)
- Automatic documentation at /docs
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer
import time

from api.routers import products, inventory, orders, automations, auth
from core.config import settings
from core.database import close_database, init_database
from core.logging import configure_logging, get_logger

# Configure logging on module load
configure_logging()
logger = get_logger(__name__)

# Security scheme for JWT
de_security = HTTPBearer(auto_error=False)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan manager.
    
    Handles startup and shutdown events:
    - Startup: Initialize database, connect to services
    - Shutdown: Close connections, cleanup
    
    Args:
        app: FastAPI application instance
        
    Yields:
        None: Control to application during runtime
    """
    # Startup
    logger.info(
        "Starting up Supply Chain Automation Platform",
        version=settings.app_version,
        environment=settings.environment
    )
    
    try:
        await init_database()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error("Failed to initialize database", error=str(e))
        raise
    
    yield
    
    # Shutdown
    logger.info("Shutting down application")
    await close_database()
    logger.info("Cleanup completed")


def create_application() -> FastAPI:
    """
    Application factory pattern.
    
    Creates and configures FastAPI instance with all middleware,
    routers, and handlers.
    
    Returns:
        FastAPI: Configured application instance
    """
    app = FastAPI(
        title=settings.app_name,
        description="""
        Advanced Supply Chain Automation Platform API.
        
        ## Features
        
        * **Products**: Full CRUD with soft delete
        * **Inventory**: Real-time stock tracking with alerts
        * **Orders**: Multi-channel order management
        * **Automations**: Rule-based workflow engine
        * **Integrations**: Shopify, Amazon SP-API sync
        
        ## Authentication
        
        All endpoints require JWT authentication via Bearer token.
        Use `/auth/login` to obtain tokens.
        """,
        version=settings.app_version,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )
    
    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.debug else [],  # Configure for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # GZip compression
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    
    # Request logging middleware
    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        """Log all HTTP requests with timing."""
        start_time = time.time()
        
        # Log request
        logger.info(
            "Request started",
            method=request.method,
            path=request.url.path,
            client=request.client.host if request.client else None
        )
        
        response = await call_next(request)
        
        # Log response
        duration = time.time() - start_time
        logger.info(
            "Request completed",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=round(duration * 1000, 2)
        )
        
        return response
    
    # Exception handlers
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """Handle all unhandled exceptions."""
        logger.error(
            "Unhandled exception",
            error=str(exc),
            path=request.url.path,
            exc_info=True
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "Internal server error",
                "detail": str(exc) if settings.debug else "An unexpected error occurred"
            }
        )
    
    # Health check endpoint
    @app.get("/health", tags=["Health"], include_in_schema=False)
    async def health_check() -> dict:
        """
        Simple health check endpoint.
        
        Returns:
            dict: Health status
        """
        return {
            "status": "healthy",
            "version": settings.app_version,
            "environment": settings.environment
        }
    
    # Root endpoint
    @app.get("/", tags=["Root"])
    async def root() -> dict:
        """
        API root with basic info.
        
        Returns:
            dict: API information
        """
        return {
            "name": settings.app_name,
            "version": settings.app_version,
            "docs": "/docs",
            "health": "/health"
        }
    
    # Include routers
    app.include_router(
        auth.router,
        prefix=f"{settings.api_prefix}/auth",
        tags=["Authentication"]
    )
    app.include_router(
        products.router,
        prefix=f"{settings.api_prefix}/products",
        tags=["Products"]
    )
    app.include_router(
        inventory.router,
        prefix=f"{settings.api_prefix}/inventory",
        tags=["Inventory"]
    )
    app.include_router(
        orders.router,
        prefix=f"{settings.api_prefix}/orders",
        tags=["Orders"]
    )
    app.include_router(
        automations.router,
        prefix=f"{settings.api_prefix}/automations",
        tags=["Automations"]
    )
    
    return app


# Create application instance
app = create_application()


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug,
        log_level=settings.log_level.lower()
    )
