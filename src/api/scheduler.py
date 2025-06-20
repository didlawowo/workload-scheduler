from fastapi import APIRouter, HTTPException, Path, Body
from loguru import logger
from pydantic import BaseModel
from core.dbManager import DatabaseManager
from core.models import WorkloadSchedule
from utils.clean_cron import clean_cron_expression
from typing import List, Optional, Dict, Any
from cron_validator import CronValidator
from datetime import datetime

scheduler = APIRouter(tags=["Schedule Management"])
db_manager = DatabaseManager()

class ScheduleResponse(BaseModel):
    """
    Modèle de réponse pour les opérations sur les programmations.
    """
    status: str
    detail: Optional[str] = None


@scheduler.get(
    "/schedules",
    response_model=List[WorkloadSchedule],
    summary="Get all workload schedules",
    description="Retrieve all scheduled workload operations"
)
async def get_schedules() -> List[WorkloadSchedule]:
    """
    Récupère toutes les programmations de workload.

    Returns:
        Liste de toutes les programmations enregistrées
    """
    try:
        logger.debug("GET /schedules")
        schedules = await db_manager.get_all_schedules()
        return schedules
    except Exception as e:
        logger.error(f"Error in GET /schedules: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@scheduler.get(
    "/schedule/{uid}",
    response_model=Optional[WorkloadSchedule],
    summary="Get workload by uid",
    description="Retrieve one scheduled workload operation"
)
async def get_schedule_by_uid(uid: str) -> Optional[WorkloadSchedule]:
    """
    Récupère une programmation par son UID.

    Args:
        uid: Identifiant unique du workload
    Returns:
        La programmation correspondante ou None si non trouvée
    """
    try:
        logger.debug(f"GET /schedule/{uid}")
        schedule = await db_manager.get_schedule(uid)

        if not schedule:
            logger.info(f"Aucun schedule trouvé pour l'UID: {uid}")
            raise HTTPException(status_code=404, detail="Schedule not found")


        logger.info(f"Schedule trouvé pour l'UID: {uid}, ID: {schedule.id}")
        return schedule
    except Exception as e:
        logger.error(f"Erreur lors de la récupération de la programmation {uid}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def prepare_schedule_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Prépare les données de programmation en validant et nettoyant les expressions cron
    et en convertissant les dates.
    
    Args:
        data: Données de programmation brutes
    Returns:
        Données de programmation validées et nettoyées
    Raises:
        ValueError: Si une expression cron est invalide
    """
    if isinstance(data.get("last_update"), str):
        try:
            data["last_update"] = datetime.fromisoformat(data["last_update"].replace("Z", "+00:00"))
        except ValueError:
            data["last_update"] = datetime.utcnow()

    if data.get("cron_start"):
        data["cron_start"] = clean_cron_expression(data["cron_start"])
        if not CronValidator.parse(data["cron_start"]):
            raise ValueError(f"Invalid CRON expression in cron_start: {data['cron_start']}")

    if data.get("cron_stop"):
        data["cron_stop"] = clean_cron_expression(data["cron_stop"])
        if not CronValidator.parse(data["cron_stop"]):
            raise ValueError(f"Invalid CRON expression in cron_stop: {data['cron_stop']}")
            
    return data


@scheduler.post(
    "/schedule",
    response_model=ScheduleResponse,
    summary="Create a new schedule",
    description="Schedule a new workload operation"
)
async def create_schedule(
    schedule: WorkloadSchedule = Body(..., description="The schedule details to create")
) -> ScheduleResponse:
    """
    Crée une nouvelle programmation de workload.

    Args:
        schedule: Détails de la programmation à créer
    Returns:
        Un objet ScheduleResponse indiquant le succès de l'opération
    """
    try:
        data = schedule.model_dump()
        validated_data = prepare_schedule_data(data)
        
        await db_manager.store_schedule_status(validated_data)
        logger.success("POST /schedule - Created schedule")
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
) -> ScheduleResponse:
    """
    Met à jour une programmation existante.

    Args:
        schedule_id: ID de la programmation à mettre à jour
        schedule: Nouvelles données de la programmation
    Returns:
        Un objet ScheduleResponse indiquant le succès de l'opération
    """
    try:
        data = schedule.model_dump()
        validated_data = prepare_schedule_data(data)
        
        updated_schedule = WorkloadSchedule(**validated_data)
        success = await db_manager.update_schedule(schedule_id, updated_schedule)
        
        if not success:
            logger.warning(f"Schedule with ID {schedule_id} not found")
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
) -> ScheduleResponse:
    """
    Supprime une programmation existante.

    Args:
        schedule_id: ID de la programmation à supprimer
    Returns:
        Un objet ScheduleResponse indiquant le succès de l'opération
    """
    logger.info(f"DELETE /schedules/{schedule_id}")
    try:
        logger.debug(f"Attempting to delete schedule with ID {schedule_id}")
        success = await db_manager.delete_schedule(schedule_id)

        if not success:
            logger.warning(f"Schedule with ID {schedule_id} not found")
            raise HTTPException(status_code=404, detail="Schedule not found")
        logger.info(f"Successfully deleted schedule with ID {schedule_id}")
        return {"status": "deleted"}
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error deleting schedule with ID {schedule_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error deleting schedule: {str(e)}")


@scheduler.put(
    "/schedule/{uid}/remove-crons",
    response_model=ScheduleResponse,
    summary="Remove cron expressions from a schedule",
    description="Remove cron expressions from an existing schedule without deleting the schedule"
)
async def remove_crons_from_schedule(
    uid: str = Path(..., description="UID of the workload to update")
) -> ScheduleResponse:
    """
    Supprime les expressions cron d'une programmation existante sans supprimer la programmation elle-même.
    
    Args:
        uid: UID du workload dont on veut supprimer les crons
    Returns:
        Un objet ScheduleResponse indiquant le succès de l'opération
    """
    logger.info(f"PUT /schedule/{uid}/remove-crons")
    try:
        schedule = await db_manager.get_schedule(uid)
        
        if not schedule:
            logger.warning(f"Schedule with UID {uid} not found")
            raise HTTPException(status_code=404, detail="Schedule not found")
        
        schedule.cron_start = ""
        schedule.cron_stop = ""
        schedule.status = "not scheduled"
        schedule.last_update = datetime.utcnow()
        
        success = await db_manager.update_schedule(schedule.id, schedule)
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to update schedule")
        
        logger.info(f"Successfully removed cron expressions from schedule with UID {uid}")
        return {"status": "updated", "detail": "Cron expressions removed"}
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error removing cron expressions from schedule with UID {uid}: {e}")
        raise HTTPException(status_code=500, detail=f"Error updating schedule: {str(e)}")