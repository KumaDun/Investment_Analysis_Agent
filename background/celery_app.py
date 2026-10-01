import os
from celery import Celery
from celery.schedules import crontab

app = Celery(
    "investanalysis",
    broker = os.getenv(
        "INVEST_CELERY_BROKER_URL",
        "redis://localhost:6379/1"
    ),
    include = ["background.tasks"],
    task_routes={
        "background.scan_filings": {"queue": "scans"},
        "background.download_job": {"queue": "downloads"},
    },
)

app.conf.update(
    task_serializer = "json",
    accept_content = ["json"],
    task_default_queue = "maintenance",
)

app.conf.timezone = "Asia/Singapore"
app.conf.beat_schedule = {
    "publish-download-jobs": {
        "task": "background.publish_download_jobs",
        "schedule": 30.0,
        "kwargs": {"limit": 100},
        "options": {"queue": "maintenance"},
    },
    "scan-quarterly-filings": {
        "task": "background.scan_filings",
        "schedule": crontab(hour=2, minute=0),
        "args": (["DIS", "NVDA"], 4),
        "options": {"queue": "scans"},
    },
}