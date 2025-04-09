from sqlmodel import Session, select
from .models import WorkloadSchedule
from .init_db import engine

def add_schedule(name, start_time, end_time):
    with Session(engine) as session:
        schedule = WorkloadSchedule(name=name, start_time=start_time, end_time=end_time)
        session.add(schedule)
        session.commit()

def get_all_schedules():
    with Session(engine) as session:
        return session.exec(select(WorkloadSchedule)).all()
