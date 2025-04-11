from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime

class WorkloadSchedule(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    start_time: datetime
    end_time: datetime
    status: str = "scheduled"
    active: bool = True
