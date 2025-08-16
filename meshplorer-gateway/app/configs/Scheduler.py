from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.pool import ThreadPoolExecutor, ProcessPoolExecutor
from pytz import utc

Scheduler = BackgroundScheduler(
    jobstores={"default": SQLAlchemyJobStore(url="sqlite:///jobs.sqlite")},
    executors={
        "default": ThreadPoolExecutor(20),
        "processpool": ProcessPoolExecutor(5),
    },
    job_defaults={"coalesce": False, "max_instances": 10},
    timezone=utc,
)


def start_scheduler():
    Scheduler.start()


def shutdown_scheduler():
    Scheduler.shutdown()
