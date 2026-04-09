"""
Celery application configuration.

Configures Celery with Redis broker for distributed task processing.
"""

from celery import Celery
from celery.signals import setup_logging

from core.config import settings
from core.logging import configure_logging

# Create Celery app
celery_app = Celery(
    "supply_chain",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "workers.tasks.sync",
        "workers.tasks.automation_engine",
    ]
)

# Celery configuration
celery_app.conf.update(
    # Serialization
    task_serializer=settings.celery_task_serializer,
    accept_content=settings.celery_accept_content,
    result_serializer="json",
    
    # Task execution
    task_track_started=True,
    task_time_limit=3600,  # 1 hour
    task_soft_time_limit=3000,  # 50 minutes
    
    # Worker settings
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,
    
    # Result backend
    result_expires=86400,  # 24 hours
    result_extended=True,
    
    # Retry settings
    task_default_retry_delay=60,  # 1 minute
    task_max_retries=3,
    
    # Queue configuration
    task_default_queue="default",
    task_queues={
        "default": {"exchange": "default", "routing_key": "default"},
        "sync": {"exchange": "sync", "routing_key": "sync"},
        "automations": {"exchange": "automations", "routing_key": "automations"},
        "high_priority": {"exchange": "high_priority", "routing_key": "high_priority"},
    },
    task_routes={
        "workers.tasks.sync.*": {"queue": "sync"},
        "workers.tasks.automation_engine.*": {"queue": "automations"},
    },
    
    # Beat schedule (periodic tasks)
    beat_schedule={
        "sync-shopify-inventory": {
            "task": "workers.tasks.sync.sync_shopify_inventory",
            "schedule": 300.0,  # Every 5 minutes
            "options": {"queue": "sync"}
        },
        "sync-amazon-orders": {
            "task": "workers.tasks.sync.sync_amazon_orders",
            "schedule": 600.0,  # Every 10 minutes
            "options": {"queue": "sync"}
        },
        "check-automation-triggers": {
            "task": "workers.tasks.automation_engine.check_all_triggers",
            "schedule": 60.0,  # Every minute
            "options": {"queue": "automations"}
        },
    },
    
    # Timezone
    timezone="UTC",
    enable_utc=True,
)


@setup_logging.connect
def setup_celery_logging(**kwargs):
    """Configure logging for Celery workers."""
    configure_logging()


if __name__ == "__main__":
    celery_app.start()
