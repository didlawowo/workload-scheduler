from sqlmodel import Session, select
from .models import WorkloadSchedule
from .init_db import engine

def add_schedule(schedule: WorkloadSchedule):
    with Session(engine) as session:
        session.add(schedule)
        session.commit()

def get_all_schedules():
    with Session(engine) as session:
        return session.exec(select(WorkloadSchedule)).all()

def delete_schedule(schedule_id: int):
    with Session(engine) as session:
        schedule = session.get(WorkloadSchedule, schedule_id)
        if not schedule:
            return False
        session.delete(schedule)
        session.commit()
        return True
