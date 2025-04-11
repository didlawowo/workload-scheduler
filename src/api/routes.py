from fastapi import APIRouter, HTTPException
from loguru import logger
from core.db import add_schedule, get_all_schedules, delete_schedule
from core.models import WorkloadScheduleCreate, WorkloadSchedule

router = APIRouter()

@router.get("/schedules", response_model=list[WorkloadSchedule])
def get_schedules():
    logger.info("GET /schedules")
    return get_all_schedules()

@router.post("/schedules")
def create_schedule(schedule: WorkloadScheduleCreate):
    new_schedule = WorkloadSchedule(**schedule.model_dump())
    add_schedule(new_schedule)
    logger.info("POST /schedules")
    return {"status": "created"}

@router.delete("/schedules/{schedule_id}")
def delete_schedule_route(schedule_id: int):
    logger.info(f"DELETE /schedules/{schedule_id}")
    success = delete_schedule(schedule_id)
    if not success:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return {"status": "deleted"}
