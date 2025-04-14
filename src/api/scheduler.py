from fastapi import APIRouter, HTTPException, Path, Body
from loguru import logger
from pydantic import BaseModel
from core.db import add_schedule, get_all_schedules, delete_schedule, update_schedule
from core.models import WorkloadSchedule
from icecream import ic
from datetime import datetime
from typing import List

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
    logger.info("GET /schedules")
    return get_all_schedules()

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
            
        new_schedule = WorkloadSchedule(**data)
        add_schedule(new_schedule)
        logger.success("POST /schedules")
        return {"status": "created"}
    except Exception as e:
        ic(e)
        logger.error(f"Error creating schedule: {e}")
        raise HTTPException(status_code=400)
        
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
        success = update_schedule(schedule_id, schedule)
        if not success:
            raise HTTPException(status_code=404, detail="Schedule not found")
        return {"status": "updated"}
    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"Error updating schedule: {e}")
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
