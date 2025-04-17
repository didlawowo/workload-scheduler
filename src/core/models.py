from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime
from pydantic import field_validator
from crontab import CronSlices

class WorkloadSchedule(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    start_time: datetime
    end_time: datetime
    status: str = "scheduled"
    active: bool = True
    cron_start: Optional[str] = None
    cron_stop: Optional[str] = None
    
    @field_validator("cron_start", "cron_stop")
    @classmethod
    def validate_cron(cls, v):
        if v is not None and not CronSlices.is_valid(v):
            raise ValueError("Invalid CRON expression")
        return v