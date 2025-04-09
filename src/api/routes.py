from fastapi import APIRouter
from loguru import logger
from core.db import add_schedule, get_all_schedules
from core.models import WorkloadScheduleCreate

router = APIRouter()

@router.get("/schedules", response_model=list[WorkloadScheduleCreate])
def get_schedules():
    logger.info("GET /schedules")
    return get_all_schedules()

@router.post("/schedules")
def create_schedule(schedule: WorkloadScheduleCreate):
    add_schedule(schedule.name, schedule.start_time, schedule.end_time)
    logger.info("POST /schedules")
    return {"status": "created"}
