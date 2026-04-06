"""
APScheduler-based job scheduler.
Runs scraping + analysis pipeline on configurable intervals.
"""
# --- path anchor: must be before any project imports ---
import sys
from pathlib import Path
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
# -------------------------------------------------------

import logging
import os

import yaml
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from main import run_pipeline

logger = logging.getLogger(__name__)


def load_config(path: str = "config.yaml") -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_scheduler(config: dict | None = None) -> BlockingScheduler:
    cfg = config or load_config()
    sched_cfg = cfg.get("scheduler", {})

    scheduler = BlockingScheduler(timezone="Africa/Casablanca")

    interval_hours = sched_cfg.get("interval_hours", 6)
    cron_expr = sched_cfg.get("cron", None)

    if cron_expr:
        trigger = CronTrigger.from_crontab(cron_expr, timezone="Africa/Casablanca")
        logger.info("Scheduler: using cron expression '%s'", cron_expr)
    else:
        trigger = IntervalTrigger(hours=interval_hours)
        logger.info("Scheduler: running every %d hour(s)", interval_hours)

    scheduler.add_job(
        func=lambda: run_pipeline(cfg),
        trigger=trigger,
        id="legal_monitor_pipeline",
        name="Moroccan Legal Monitoring Pipeline",
        misfire_grace_time=300,
        coalesce=True,
        max_instances=1,
    )

    return scheduler


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
    )
    cfg = load_config()
    scheduler = build_scheduler(cfg)
    logger.info("Scheduler started. Press Ctrl+C to stop.")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped.")
