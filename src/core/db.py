from loguru import logger
from sqlmodel import Session, select
from .models import WorkloadSchedule
# from .init_db import engine
from icecream import ic
from crontab import CronSlices
from core.dbManager import DatabaseManager
D = DatabaseManager()

engine = D.engine # todo delete it
def add_schedule(schedule: WorkloadSchedule):
    with Session(engine) as session:
        session.add(schedule)
        session.commit()
        session.refresh(schedule)
        schedule_id = schedule.id
    return schedule_id

def get_all_schedules():
    try:
        with Session(engine) as session:
            statement = select(WorkloadSchedule)
            results = session.exec(statement)
            schedules = results.all()
            return schedules
    except Exception as e:
        logger.error(f"Error fetching schedules: {e}")
        ic(e)
        raise e

def update_schedule(schedule_id: int, updated_schedule: WorkloadSchedule):
    with Session(engine) as session:
        schedule = session.get(WorkloadSchedule, schedule_id)
        if not schedule:
            return False

        schedule_data = updated_schedule.model_dump(exclude={"id"})

        for key, value in schedule_data.items():
            setattr(schedule, key, value)

        if schedule.cron and not CronSlices.is_valid(schedule.cron):
            raise ValueError("Invalid CRON expression")

        session.add(schedule)
        session.commit()
        return True

def delete_schedule(schedule_id: int):
    with Session(engine) as session:
        schedule = session.get(WorkloadSchedule, schedule_id)
        if not schedule:
            return False
        session.delete(schedule)
        session.commit()
        return True
