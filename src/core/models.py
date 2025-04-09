from sqlalchemy import Column, Integer, String, DateTime, Boolean
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class WorkloadSchedule(Base):
    __tablename__ = 'workload_schedules'

    id = Column(Integer, primary_key=True)
    name = Column(String)
    start_time = Column(DateTime)
    end_time = Column(DateTime)
    status = Column(String)
    active = Column(Boolean, default=True)
