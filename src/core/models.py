from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime
from pydantic import field_validator
from cron_validator import CronValidator
from enum import Enum
from utils.clean_cron import clean_cron_expression

class ScheduleStatus(str, Enum):
    NOT_SCHEDULED = "not scheduled"
    SCHEDULED = "scheduled"

class WorkloadSchedule(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    uid: str
    last_update: datetime = Field(default_factory=datetime.utcnow)
    status: ScheduleStatus = ScheduleStatus.NOT_SCHEDULED
    active: bool = True
    cron_start: Optional[str] = Field(default=None, nullable=True)
    cron_stop: Optional[str] = Field(default=None, nullable=True)

    @field_validator("cron_start", "cron_stop")
    @classmethod
    def validate_cron(cls, v):
        if v is None:
            return v
        v = clean_cron_expression(v)

        if not CronValidator.parse(v):
            raise ValueError(f"Invalid CRON expression: {v}")
        return v

    @classmethod
    def from_api_response(cls, schedule: dict):
        """🏭 Crée une instance depuis la réponse API"""

        last_update = schedule.get("last_update")
        if isinstance(last_update, str):
            try:
                last_update = datetime.fromisoformat(last_update.replace("Z", "+00:00"))
            except ValueError:
                last_update = datetime.utcnow()
        elif last_update is None:
            last_update = datetime.utcnow()
        
        status = schedule.get("status")
        if isinstance(status, str):
            try:
                status = ScheduleStatus(status)
            except ValueError:
                status = ScheduleStatus.SCHEDULED
        elif status is None:
            status = ScheduleStatus.NOT_SCHEDULED

        cron_start = schedule.get("cron_start")
        if cron_start:
            cron_start = clean_cron_expression(cron_start)
            
        cron_stop = schedule.get("cron_stop")
        if cron_stop:
            cron_stop = clean_cron_expression(cron_stop)
            
        return cls(
            name=schedule["name"],
            uid=schedule["uid"],
            active=schedule.get("active", True),
            status=status,
            last_update=last_update,
            cron_start=cron_start,
            cron_stop=cron_stop,
        )
