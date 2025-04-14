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
    
def update_schedule(schedule_id: int, updated_schedule: WorkloadSchedule):
    with Session(engine) as session:
        schedule = session.get(WorkloadSchedule, schedule_id)
        if not schedule:
            return False
        
        schedule_data = updated_schedule.model_dump(exclude={"id"})
        for key, value in schedule_data.items():
            setattr(schedule, key, value)
        
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
