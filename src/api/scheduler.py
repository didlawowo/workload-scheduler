from fastapi import APIRouter, HTTPException, Path, Body
from loguru import logger
from pydantic import BaseModel
from core.db import add_schedule, get_all_schedules, delete_schedule, update_schedule
from core.models import WorkloadSchedule
from icecream import ic
from datetime import datetime
from typing import List
from crontab import CronSlices

scheduler = APIRouter(tags=["Schedule Management"])

class ScheduleResponse(BaseModel):
    status: str
    detail: str = None

@scheduler.get(
    "/schedules",
    response_model=List[WorkloadSchedule],
    summary="Get all workload schedules",
    description="Retrieve all scheduled workload operations"
)
def get_schedules():
    try:
        logger.info("GET /schedules")
        return get_all_schedules()
    except Exception as e:
        logger.error(f"Error in GET /schedules: {e}")
        ic(e)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
@scheduler.post(
    "/schedules",
    response_model=ScheduleResponse,
    summary="Create a new schedule",
    description="Schedule a new workload operation"
)
def create_schedule(
    schedule: WorkloadSchedule = Body(..., description="The schedule details to create")
):
    try:
        data = schedule.model_dump()
        if isinstance(data["start_time"], str):
            data["start_time"] = datetime.fromisoformat(data["start_time"])
        if isinstance(data["end_time"], str):
            data["end_time"] = datetime.fromisoformat(data["end_time"])
        if data.get("cron"):
            if not CronSlices.is_valid(data["cron"]):
                raise ValueError("Invalid CRON expression")
        new_schedule = WorkloadSchedule(**data)
        schedule_id = add_schedule(new_schedule)
        logger.success(f"POST /schedules - Created schedule with id: {schedule_id}")
        return {"status": "created", "detail": f"Schedule created with ID: {schedule_id}"}
    except ValueError as ve:
        logger.error(f"Validation error: {ve}")
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Error creating schedule: {e}")
        logger.error(f"Error type: {type(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@scheduler.put(
    "/schedules/{schedule_id}",
    response_model=ScheduleResponse,
    summary="Update an existing schedule",
    description="Modify details of an existing schedule"
)
async def update_schedule_route(
    schedule_id: int = Path(..., description="ID of the schedule to update"),
    schedule: WorkloadSchedule = Body(..., description="The updated schedule details")
):
    try:
        data = schedule.model_dump()
        if isinstance(data.get("start_time"), str):
            data["start_time"] = datetime.fromisoformat(data["start_time"])
        if isinstance(data.get("end_time"), str):
            data["end_time"] = datetime.fromisoformat(data["end_time"])

        updated_schedule = WorkloadSchedule(**data)

        success = update_schedule(schedule_id, updated_schedule)
        if not success:
            raise HTTPException(status_code=404, detail="Schedule not found")
        return {"status": "updated"}
    except ValueError as ve:
        logger.error(f"Validation error: {ve}")
        raise HTTPException(status_code=400, detail=str(ve))
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error updating schedule: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@scheduler.delete(
    "/schedules/{schedule_id}",
    response_model=ScheduleResponse,
    summary="Delete a schedule",
    description="Remove an existing schedule"
)
def delete_schedule_route(
    schedule_id: int = Path(..., description="ID of the schedule to delete")
):
    logger.info(f"DELETE /schedules/{schedule_id}")
    success = delete_schedule(schedule_id)
    if not success:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return {"status": "deleted"}
