from fastapi import APIRouter, HTTPException, Path, Body
from loguru import logger
from pydantic import BaseModel
from core.dbManager import DatabaseManager
from core.models import WorkloadSchedule
from icecream import ic
from typing import List
from crontab import CronSlices

scheduler = APIRouter(tags=["Schedule Management"])
db_manager = DatabaseManager()

class ScheduleResponse(BaseModel):
    status: str
    detail: str = None

@scheduler.get(
    "/schedules",
    response_model=List[WorkloadSchedule],
    summary="Get all workload schedules",
    description="Retrieve all scheduled workload operations"
)
async def get_schedules(): # TODO: change to async
    try:
        logger.info("GET /schedules")
        schedules = await db_manager.get_all_schedules()
        return schedules
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
async def create_schedule(
    schedule: WorkloadSchedule = Body(..., description="The schedule details to create")
):
    try:
        data = schedule.model_dump()

        if data.get("cron_start"):
            if not CronSlices.is_valid(data["cron_start"]):
                raise ValueError("Invalid CRON expression in cron_start")

        if data.get("cron_stop"):
            if not CronSlices.is_valid(data["cron_stop"]):
                raise ValueError("Invalid CRON expression in cron_stop")

        await db_manager.store_schedule_status(data)
        logger.success("POST /schedules - Created schedule")
        return {"status": "created", "detail": "Schedule created successfully"}
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

        updated_schedule = WorkloadSchedule(**data)

        success = await db_manager.update_schedule(schedule_id, updated_schedule)
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
async def delete_schedule_route(
    schedule_id: int = Path(..., description="ID of the schedule to delete")
):
    logger.info(f"DELETE /schedules/{schedule_id}")
    success = await db_manager.delete_schedule(schedule_id)
    if not success:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return {"status": "deleted"}
