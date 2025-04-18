from datetime import datetime
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlmodel import select, text


from .models import WorkloadSchedule

from icecream import ic
from crontab import CronSlices

Base = declarative_base()
DATABASE_URL = "sqlite+aiosqlite:///data/schedule.db"


class DatabaseManager: # TODO look at this and Learn IT
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

    async def store_schedule_status(self, schedule: dict):
        """💾 Stocke le statut d'un appareil"""

        async with self.async_session() as session:
            try:
                ic(schedule)
                schedule = WorkloadSchedule.from_api_response(schedule)

                session.add(schedule)
                await session.commit()
                logger.success(f"✅ Statut stocké pour l'appareil {schedule.uid}")
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
                ic(e)
                raise e

    async def update_schedule(self, schedule_id: int, updated_schedule: WorkloadSchedule):
        async with self.async_session() as session:
            schedule = await session.get(WorkloadSchedule, schedule_id)
            if not schedule:
                logger.error(f"Schedule with ID {schedule_id} not found")
                return False

            schedule_data = updated_schedule.model_dump(exclude={"id"})

            if "last_update" in schedule_data and isinstance(schedule_data["last_update"], str):
                schedule_data["last_update"] = datetime.fromisoformat(schedule_data["last_update"])

            for key, value in schedule_data.items():
                setattr(schedule, key, value)

            if hasattr(schedule, 'cron_start') and schedule.cron_start:
                if not CronSlices.is_valid(schedule.cron_start):
                    raise ValueError("Invalid CRON expression in cron_start")

            if hasattr(schedule, 'cron_stop') and schedule.cron_stop:
                if not CronSlices.is_valid(schedule.cron_stop):
                    raise ValueError("Invalid CRON expression in cron_stop")

            if hasattr(schedule, 'cron') and schedule.cron:
                if not CronSlices.is_valid(schedule.cron):
                    raise ValueError("Invalid CRON expression in cron")

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