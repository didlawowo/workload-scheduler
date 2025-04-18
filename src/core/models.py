from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime
from pydantic import field_validator
from crontab import CronSlices

class WorkloadSchedule(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    uid: str
    last_update: datetime = Field(default_factory=datetime.utcnow)
    status: str = "not scheduled" # TODO faire une enum 
    active: bool = True
    cron_start: Optional[str] =  Field(default=None, nullable=True)
    cron_stop: Optional[str] = Field(default=None, nullable=True)
    
    @field_validator("cron_start", "cron_stop")
    @classmethod
    def validate_cron(cls, v):
        if v is not None and not CronSlices.is_valid(v):
            raise ValueError("Invalid CRON expression")
        return v
    
    @classmethod
    def from_api_response(cls, schedule: dict): # TODO look at this
        """🏭 Crée une instance depuis la réponse API"""
        return cls(
            name=schedule["name"],
            uid=schedule["uid"],
            active=schedule["active"],
            status=schedule["status"],
            last_update=schedule["last_update"],
            cron_start=schedule.get("cron_start"),
            cron_stop=schedule.get("cron_stop"),
        )