from fastapi import APIRouter, HTTPException
from loguru import logger
from core.db import add_schedule, get_all_schedules, delete_schedule
from core.models import WorkloadSchedule
from icecream import ic
from datetime import datetime

scheduler = APIRouter()

@scheduler.get("/schedules", response_model=list[WorkloadSchedule])
def get_schedules():
    logger.info("GET /schedules")
    return get_all_schedules()

@scheduler.post("/schedules")
def create_schedule(schedule: WorkloadSchedule):
    try:
        data = schedule.model_dump()
        if isinstance(data["start_time"], str):
            data["start_time"] = datetime.fromisoformat(data["start_time"])
        if isinstance(data["end_time"], str):
            data["end_time"] = datetime.fromisoformat(data["end_time"])
            
        new_schedule = WorkloadSchedule(**data)
        add_schedule(new_schedule)
        logger.success("POST /schedules")
        return {"status": "created"}
    except Exception as e:
        ic(e)
        logger.error(f"Error creating schedule: {e}")
        raise HTTPException(status_code=400)
        
# rajouter un PUT pour changer la db

@scheduler.delete("/schedules/{schedule_id}")
def delete_schedule_route(schedule_id: int):
    logger.info(f"DELETE /schedules/{schedule_id}")
    success = delete_schedule(schedule_id)
    if not success:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return {"status": "deleted"}
