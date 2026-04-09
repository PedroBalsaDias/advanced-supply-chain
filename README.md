# Advanced Supply Chain Automation Platform

A comprehensive, production-ready Supply Chain Management system built with modern Python technologies. Designed to impress recruiters with enterprise-grade architecture, async processing, and multi-channel e-commerce integrations.

## Features

### Core Capabilities
- **Product Catalog Management** - Full CRUD with soft delete, pagination, and filtering
- **Inventory Management** - Real-time stock tracking, movement history, low-stock alerts
- **Order Management** - Multi-channel order processing (Shopify, Amazon, Direct)
- **Automation Engine** - Rule-based workflows with triggers and actions
- **Audit Logging** - Complete audit trail for compliance

### Technical Highlights
- **FastAPI** - Modern, fast web framework with automatic API documentation
- **Async/Await** - Full async database operations with SQLAlchemy 2.0
- **Celery + Redis** - Distributed task queue for background processing
- **JWT Authentication** - Secure token-based authentication
- **Docker** - Containerized deployment with multi-stage builds
- **PostgreSQL** - Robust relational database with asyncpg
- **Comprehensive Testing** - Pytest with async test support

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        API Layer                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │   Products   │  │  Inventory   │  │     Orders       │   │
│  └──────────────┘  └──────────────┘  └──────────────────┘   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │  Automations │  │     Auth     │  │   Integrations   │   │
│  └──────────────┘  └──────────────┘  └──────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────────┐
│                      Business Logic                          │
│              (Services, Validation, Rules)                   │
└─────────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────────┐
│                      Data Layer                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │  PostgreSQL  │  │    Redis     │  │   Celery Queue   │   │
│  │   (Async)    │  │   (Cache)    │  │   (Background)   │   │
│  └──────────────┘  └──────────────┘  └──────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────────┐
│                   External Integrations                      │
│        ┌──────────────┐              ┌──────────────┐       │
│        │   Shopify    │              │    Amazon    │       │
│        │   (GraphQL)  │              │  (SP-API)    │       │
│        └──────────────┘              └──────────────┘       │
└─────────────────────────────────────────────────────────────┘
```

## Quick Start

### Prerequisites
- Python 3.9+
- Docker and Docker Compose
- PostgreSQL 14+ (if running locally)
- Redis 7+ (if running locally)

### Docker Setup (Recommended)

```bash
# Clone the repository
git clone <repository-url>
cd advanced-supply-chain

# Copy environment file
cp .env.example .env

# Edit .env with your configuration
# At minimum, update SECRET_KEY for production

# Start all services
docker-compose up -d

# View logs
docker-compose logs -f api

# Stop services
docker-compose down

# Stop and remove volumes (WARNING: data will be lost)
docker-compose down -v
```

### Local Development Setup

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Setup environment variables
cp .env.example .env
# Edit .env with your local settings

# Run database migrations (if using Alembic)
# alembic upgrade head

# Initialize database tables
cd api
python -c "import asyncio; from core.database import init_database; asyncio.run(init_database())"

# Start API server
uvicorn api.main:app --reload --port 8000

# Start Celery worker (in another terminal)
celery -A workers.celery_app worker --loglevel=info

# Start Celery beat scheduler (in another terminal)
celery -A workers.celery_app beat --loglevel=info
```

## API Documentation

Once running, API documentation is available at:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **Health Check**: http://localhost:8000/health

### Authentication

All API endpoints require JWT authentication except `/health` and `/auth/login`.

```bash
# Login to get tokens
curl -X POST "http://localhost:8000/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "password"}'

# Use token in subsequent requests
curl -X GET "http://localhost:8000/api/v1/products" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Example Endpoints

#### Products
```bash
# List products with pagination
curl "http://localhost:8000/api/v1/products?page=1&page_size=20" \
  -H "Authorization: Bearer TOKEN"

# Create product
curl -X POST "http://localhost:8000/api/v1/products" \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "sku": "PROD-001",
    "name": "Wireless Headphones",
    "category": "Electronics",
    "unit_price": 99.99,
    "status": "active"
  }'
```

#### Inventory
```bash
# Get inventory levels
curl "http://localhost:8000/api/v1/inventory/levels" \
  -H "Authorization: Bearer TOKEN"

# Update stock
curl -X POST "http://localhost:8000/api/v1/inventory/update/{product_id}" \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "quantity_change": 50,
    "movement_type": "inbound",
    "notes": "New shipment received"
  }'

# Get low stock alerts
curl "http://localhost:8000/api/v1/inventory/alerts/low-stock" \
  -H "Authorization: Bearer TOKEN"
```

#### Automations
```bash
# Create automation rule
curl -X POST "http://localhost:8000/api/v1/automations" \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Low Stock Alert",
    "trigger_type": "low_stock",
    "trigger_config": {"threshold": 10},
    "action_type": "send_email",
    "action_config": {
      "email_to": "buyer@company.com",
      "email_subject": "Reorder Alert"
    }
  }'

# Trigger automation manually
curl -X POST "http://localhost:8000/api/v1/automations/{id}/trigger" \
  -H "Authorization: Bearer TOKEN"
```

## Project Structure

```
advanced-supply-chain/
├── api/                        # FastAPI application
│   ├── main.py                # App entry point
│   └── routers/               # API endpoints
│       ├── auth.py            # Authentication
│       ├── products.py        # Product CRUD
│       ├── inventory.py       # Inventory management
│       ├── orders.py          # Order processing
│       └── automations.py     # Automation engine
├── core/                      # Core modules
│   ├── config.py              # Settings (Pydantic)
│   ├── database.py            # SQLAlchemy setup
│   ├── logging.py             # Structured logging
│   └── models.py              # Database models
├── workers/                   # Celery tasks
│   ├── celery_app.py          # Celery configuration
│   └── tasks/
│       ├── sync.py            # Platform sync tasks
│       └── automation_engine.py # Automation execution
├── integrations/              # External platform clients
│   ├── shopify.py             # Shopify API client
│   └── amazon.py              # Amazon SP-API client
├── tests/                     # Test suite
│   ├── conftest.py            # Pytest fixtures
│   ├── test_api.py            # API tests
│   └── test_workers.py        # Worker tests
├── Dockerfile                 # Multi-stage Docker build
├── docker-compose.yml         # Complete stack definition
├── requirements.txt           # Python dependencies
└── README.md                  # This file
```

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=. --cov-report=html

# Run specific test file
pytest tests/test_api.py

# Run with async support
pytest -v --asyncio-mode=auto

# Run tests in Docker
docker-compose run --rm api pytest
```

## Background Tasks

The platform uses Celery for background processing:

### Scheduled Tasks (Celery Beat)
- **Every 5 minutes**: Sync Shopify inventory
- **Every 10 minutes**: Sync Amazon orders
- **Every minute**: Check automation triggers

### Queues
- **default**: General tasks
- **sync**: Platform synchronization
- **automations**: Automation rule execution
- **high_priority**: Urgent tasks

### Monitoring
Access Flower (Celery monitoring) at http://localhost:5555

## Integration Guides

### Shopify Integration

1. Create a custom app in Shopify Admin
2. Configure API credentials in `.env`:
   ```
   SHOPIFY_API_KEY=your-api-key
   SHOPIFY_API_SECRET=your-api-secret
   SHOPIFY_STORE_URL=your-store.myshopify.com
   ```
3. Set up webhooks for real-time updates
4. Products and inventory will sync automatically

See `integrations/shopify.py` for detailed implementation.

### Amazon SP-API Integration

1. Register as an Amazon developer
2. Create an SP-API application
3. Authorize your seller account
4. Configure credentials in `.env`:
   ```
   AMAZON_ACCESS_KEY=your-aws-key
   AMAZON_SECRET_KEY=your-aws-secret
   AMAZON_REFRESH_TOKEN=your-refresh-token
   ```

See `integrations/amazon.py` for detailed implementation.

## Configuration

All configuration is managed via environment variables (see `.env.example`):

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql+asyncpg://...` |
| `REDIS_URL` | Redis connection string | `redis://localhost:6379/0` |
| `SECRET_KEY` | JWT signing key | Required |
| `DEBUG` | Enable debug mode | `false` |
| `LOG_LEVEL` | Logging level | `INFO` |

## Deployment

### Production Checklist

- [ ] Change `SECRET_KEY` to a secure random value
- [ ] Set `DEBUG=false`
- [ ] Configure production database
- [ ] Set up SSL/TLS certificates
- [ ] Configure proper logging
- [ ] Set up monitoring and alerting
- [ ] Configure backup strategy

### Docker Production Deployment

```bash
# Use production profile (includes Nginx)
docker-compose --profile production up -d

# Scale workers
docker-compose up -d --scale worker=4
```

### Cloud Deployment

The application is ready for deployment on:
- **AWS ECS/EKS** with RDS and ElastiCache
- **Google Cloud Run** with Cloud SQL and Memorystore
- **Azure Container Instances** with Azure SQL and Redis Cache
- **DigitalOcean App Platform**
- **Heroku** (with modifications)

## Tech Stack

| Component | Technology |
|-----------|------------|
| Web Framework | FastAPI |
| Database | PostgreSQL 15 + asyncpg |
| ORM | SQLAlchemy 2.0 |
| Cache/Queue | Redis 7 |
| Task Queue | Celery |
| Auth | JWT (python-jose) |
| Validation | Pydantic v2 |
| Logging | structlog |
| Testing | pytest + pytest-asyncio |
| Deployment | Docker + Docker Compose |

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Development Guidelines

- Follow PEP 8 style guide
- Add type hints to all functions
- Write docstrings in Google format
- Include tests for new features
- Maintain >80% code coverage

## License

This project is licensed under the MIT License.

## Contact

For questions or support, please contact:
- Email: Pedro.b.o.dias@gmail.com
- Git: PedroBalsaDias

---

Built with by Pedro B. Dias for NOVAEO Supply Chain Systems & Automations Specialist position.
