from datetime import datetime
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlmodel import select, text
from .models import WorkloadSchedule
from utils.clean_cron import clean_cron_expression
from icecream import ic  # noqa: F401
from cron_validator import CronValidator
from typing import Dict, Any

Base = declarative_base()
DATABASE_URL = "sqlite+aiosqlite:///data/schedule.db"


class DatabaseManager:
    def __init__(self):
        """🗄️ Initialise la connexion à la base de données"""
        self.engine = create_async_engine(DATABASE_URL, echo=False)
        self.async_session = async_sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )

    async def create_table(self):
        """Crée les tables de manière asynchrone"""
        logger.info("Creating tables")

        async with self.engine.begin() as conn:
            # Utilise run_sync pour exécuter le code synchrone dans un contexte asynchrone
            await conn.run_sync(WorkloadSchedule.metadata.create_all)

        logger.success("All tables created")

    async def check_table_exists(self):
        async with self.engine.connect() as conn:
            result = await conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' ")
            )
            tables = result.fetchall()
            logger.info(f"Tables trouvées: {tables}")
            if len(tables) > 0:
                logger.info("Tables existantes")
                return True

            return False

    async def close(self):
        """🔌 Ferme la connexion à la base"""
        await self.engine.dispose()

    async def store_uid(self, uid: str, name: str):
        """💾 Stocke l'uid d'un deploiement s'il n'existe pas déjà"""

        async with self.async_session() as session:
            try:
                # Vérifier si l'uid existe déjà
                existing_workload = await session.execute(
                    select(WorkloadSchedule).where(WorkloadSchedule.uid == uid)
                )
                existing_workload = existing_workload.scalars().first()

                # Si l'uid existe déjà, on ne fait rien et on retourne
                if existing_workload:
                    logger.info(f"🔄 uid {uid} pour {name} existe déjà, aucune action nécessaire")
                    return

                # Sinon, on crée un nouveau workload
                workload = WorkloadSchedule(
                    name=name,
                    uid=uid,
                )

                session.add(workload)
                await session.commit()
                logger.success(f"✅ uid stocké pour {name}")

            except Exception as e:
                await session.rollback()
                logger.error(f"❌ Erreur lors du stockage: {e}")
                raise

    async def store_schedule_status(self, schedule: Dict[str, Any]):
        """💾 Stocke le statut d'un appareil"""

        async with self.async_session() as session:
            try:
                # ic(schedule)
                if isinstance(schedule.get("last_update"), str):
                    try:
                        schedule["last_update"] = datetime.fromisoformat(schedule["last_update"].replace("Z", "+00:00"))
                    except ValueError:
                        schedule["last_update"] = datetime.utcnow()

                if schedule.get("cron_start"):
                    schedule["cron_start"] = clean_cron_expression(schedule["cron_start"])
                if schedule.get("cron_stop"):
                    schedule["cron_stop"] = clean_cron_expression(schedule["cron_stop"])

                schedule_obj = WorkloadSchedule.from_api_response(schedule)

                session.add(schedule_obj)
                await session.commit()
                logger.success(f"✅ Statut stocké pour l'appareil {schedule_obj.uid}")
                return schedule_obj
            except Exception as e:
                await session.rollback()
                logger.error(f"❌ Erreur lors du stockage: {e}")
                raise

    async def get_all_schedules(self):
        """📋 Récupère tous les horaires"""
        async with self.async_session() as session:
            try:
                statement = select(WorkloadSchedule)
                results = await session.execute(statement)
                schedules = results.scalars().all()
                return schedules
            except Exception as e:
                logger.error(f"Error fetching schedules: {e}")

                raise e

    async def get_schedule(self, uid: str):
        """📋 Récupère l'horaire de l'uid"""
        async with self.async_session() as session:
            try:
                logger.info(f"Recherche du schedule pour l'UID: {uid}")
                query = select(WorkloadSchedule).where(WorkloadSchedule.uid == uid)
                results = await session.execute(query)
                schedule = results.scalars().first()

                if schedule:
                    logger.info(f"Schedule trouvé pour l'UID {uid}: ID={schedule.id}")
                else:
                    logger.info(f"Aucun schedule trouvé pour l'UID: {uid}")

                return schedule
            except Exception as e:
                logger.error(f"Erreur lors de la récupération du schedule pour l'UID {uid}: {e}")
                logger.exception(e)
                raise e

    async def update_schedule(self, schedule_id: int, updated_schedule: WorkloadSchedule):
        async with self.async_session() as session:
            schedule = await session.get(WorkloadSchedule, schedule_id)
            if not schedule:
                logger.error(f"Schedule with ID {schedule_id} not found") # TODO Gérer l'erreur coté front
                return False

            schedule_data = updated_schedule.model_dump(exclude={"id"})

            if "last_update" in schedule_data:
                if isinstance(schedule_data["last_update"], str):
                    try:
                        schedule_data["last_update"] = datetime.fromisoformat(schedule_data["last_update"].replace("Z", "+00:00"))
                    except ValueError:
                        schedule_data["last_update"] = datetime.utcnow()

            if "cron_start" in schedule_data and schedule_data["cron_start"]:
                schedule_data["cron_start"] = clean_cron_expression(schedule_data["cron_start"])

            if "cron_stop" in schedule_data and schedule_data["cron_stop"]:
                schedule_data["cron_stop"] = clean_cron_expression(schedule_data["cron_stop"])

            for key, value in schedule_data.items():
                setattr(schedule, key, value)

            if hasattr(schedule, 'cron_start') and schedule.cron_start:
                if not CronValidator.parse(schedule.cron_start):
                    raise ValueError(f"Invalid CRON expression in cron_start: {schedule.cron_start}")

            if hasattr(schedule, 'cron_stop') and schedule.cron_stop:
                if not CronValidator.parse(schedule.cron_stop):
                    raise ValueError(f"Invalid CRON expression in cron_stop: {schedule.cron_stop}")

            session.add(schedule)
            await session.commit()
            return True

    async def delete_schedule(self, schedule_id: int):
        async with self.async_session() as session:
            schedule = await session.get(WorkloadSchedule, schedule_id)
            if not schedule:
                logger.error(f"Schedule with ID {schedule_id} not found")
                return False
            logger.info(f"Deleting schedule: {schedule.id}, {schedule.name}")

            await session.delete(schedule)
            await session.commit()
            logger.info(f"Schedule {schedule_id} deleted successfully")
            return True