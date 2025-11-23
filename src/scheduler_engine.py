import asyncio
import os
from datetime import datetime

import pytz
from croniter import croniter
from icecream import ic  # noqa: F401
from loguru import logger

from core.models import ScheduleStatus, WorkloadSchedule
from utils.helpers import RetryableAsyncClient
from utils.logging_config import configure_logger

# Configure logger with JSON format for Datadog
configure_logger(service_name="workload-scheduler", component="scheduler")


class SchedulerEngine:
    """
    Moteur de scheduling qui vérifie les expressions cron pour démarrer/arrêter les workloads.

    Attributes:
        check_interval: Intervalle (en secondes) entre chaque vérification des programmations
        running: Indicateur si le scheduleur est en cours d'exécution
        _task: Tâche asyncio pour le processus en arrière-plan
        api_url: URL de l'API workload-scheduler
    """

    def __init__(self, check_interval: int = 60):
        """
        Initialise le moteur de scheduling.

        Args:
            check_interval: Intervalle de vérification en secondes (par défaut: 60)
        """
        self.check_interval = check_interval
        self.running = False
        self._task = None
        self.timezone = pytz.timezone(os.getenv("TIMEZONE", "Europe/Paris"))
        self.api_url = os.getenv("API_URL", "http://localhost:8000")
        self.client = RetryableAsyncClient()

    async def start(self):
        """
        Démarre le moteur de scheduling en arrière-plan.
        """
        if self.running:
            logger.warning("Le scheduler est déjà en cours d'exécution")
            return

        self.running = True
        self._task = asyncio.create_task(self._run())
        logger.info(
            f"⏰ Démarrage du moteur de scheduling (intervalle: {self.check_interval}s)"
        )

    async def stop(self):
        """
        Arrête le moteur de scheduling.
        """
        if not self.running:
            logger.warning("Le scheduler n'est pas en cours d'exécution")
            return

        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("🛑 Arrêt du moteur de scheduling")

    async def _run(self):
        """
        Boucle principale du moteur de scheduling.
        """
        try:
            while self.running:
                try:
                    await self._check_schedules()
                    await asyncio.sleep(self.check_interval)
                except Exception as e:
                    logger.error(f"Erreur dans la boucle de scheduling: {e}")
                    logger.exception(e)
                    await asyncio.sleep(self.check_interval)
        except asyncio.CancelledError:
            logger.info("Tâche de scheduling annulée")
            raise

    async def _check_schedules(self):
        """
        Vérifie toutes les programmations et exécute les actions nécessaires.
        """
        try:
            schedules = await self.client.get(url=f"{self.api_url}/schedules")
            schedules_dict = schedules.json()

            logger.info(f"Vérification de {len(schedules_dict)} programmations à {datetime.now(self.timezone).strftime('%H:%M:%S')}")

            if not schedules_dict:
                logger.info("Aucune programmation trouvée dans la base de données")
                return

            # Convertir les dictionnaires en objets WorkloadSchedule
            schedule_objects = [WorkloadSchedule.from_api_response(item) for item in schedules_dict]

            now = datetime.now(self.timezone)

            for schedule in schedule_objects:
                await self._process_schedule(schedule, now)

        except Exception as e:
            logger.error(f"Erreur lors de la vérification des programmations: {e}")
            logger.exception(e)

    async def _process_schedule(self, schedule: WorkloadSchedule, now: datetime):
        """
        Traite une programmation individuelle.

        Args:
            schedule: La programmation à traiter
            now: L'heure actuelle
        """
        
        try:
            should_start = self._should_execute(schedule.cron_start, now)
            should_stop = self._should_execute(schedule.cron_stop, now)

            logger.debug(
                f"Programmation {schedule.id} ({schedule.name}, UID: {schedule.uid}): status={schedule.status}, active={schedule.active}, should_start={should_start}, should_stop={should_stop}"
            )
            logger.debug(
                f"cron_start: {schedule.cron_start}, cron_stop: {schedule.cron_stop}"
            )

            if should_start and (schedule.status == ScheduleStatus.NOT_SCHEDULED or not schedule.active):
                logger.info(
                    f"Déclenchement du démarrage pour {schedule.name} (ID: {schedule.id}, UID: {schedule.uid})"
                )
                await self._start_workload(schedule)
            elif should_stop and schedule.status == ScheduleStatus.SCHEDULED and schedule.active:
                logger.info(
                    f"Déclenchement de l'arrêt pour {schedule.name} (ID: {schedule.id}, UID: {schedule.uid})"
                )
                await self._stop_workload(schedule)
            elif not schedule.active:
                logger.debug(
                    f"Programmation {schedule.id} ({schedule.name}, UID: {schedule.uid}) inactive, mais vérifiée pour un éventuel démarrage"
                )

        except Exception as e:
            logger.error(
                f"Erreur lors du traitement de la programmation {schedule.id}: {e}"
            )
            logger.exception(e)

    def _should_execute(self, cron_expression: str | None, now: datetime) -> bool:
        """
        Vérifie si une expression cron doit être exécutée.

        Args:
            cron_expression: L'expression cron à vérifier (peut être None)
            now: L'heure actuelle
        Returns:
            True si l'expression doit être exécutée, False sinon
        """
        if not cron_expression:
            return False

        try:
            cron = croniter(cron_expression, now)
            next_dt = cron.get_next(datetime)
            cron.get_prev()
            prev_dt = cron.get_prev(datetime)
            delta = (now - prev_dt).total_seconds()
            next_delta = (next_dt - now).total_seconds()

            logger.debug(
                f"Expression cron '{cron_expression}': "
                f"précédente={prev_dt}, "
                f"actuelle={now}, "
                f"prochaine={next_dt}, "
                f"delta={delta}s, "
                f"intervalle={self.check_interval}s"
            )
            return (0 <= delta < self.check_interval) or (
                0 <= next_delta < self.check_interval
            )

        except Exception as e:
            logger.error(
                f"Erreur lors du parsing de l'expression cron '{cron_expression}': {e}"
            )
            return False

    async def _start_workload(self, schedule):
        """
        Démarre un workload en utilisant son UID.
        """
        try:
            logger.info(f"🚀 Démarrage du workload: {schedule.name} (ID: {schedule.id}, UID: {schedule.uid})")

            result = await self.client.get(url=f"{self.api_url}/manage/up/deploy/{schedule.uid}")
            result_data = result.json()

            if result_data.get("status") == "success":
                # Créer un dictionnaire pour la mise à jour
                update_data = {
                    "active": True,
                    "status": ScheduleStatus.SCHEDULED.value,
                    "last_update": datetime.now(self.timezone).isoformat(),
                    "cron_start": schedule.cron_start if hasattr(schedule, 'cron_start') else None,
                    "cron_stop": schedule.cron_stop if hasattr(schedule, 'cron_stop') else None
                }

                await self.client.put(
                    url=f"{self.api_url}/schedules/{schedule.id}",
                    json=update_data
                )
                logger.success(f"✅ Workload démarré avec succès: {schedule.name}")
            else:
                logger.error(f"❌ Échec du démarrage: {result_data.get('message', 'Unknown error')}")
                
        except Exception as e:
            logger.error(f"Erreur lors du démarrage: {e}")
            logger.exception(e)
            
    async def _stop_workload(self, schedule):
        """
        Arrête un workload en utilisant son UID.

        Args:
            schedule: La programmation du workload à arrêter
        """
        try:
            logger.info(
                f"🛑 Arrêt du workload: {schedule.name} (ID: {schedule.id}, UID: {schedule.uid})"
            )

            result = await self.client.get(
                url=f"{self.api_url}/manage/down/deploy/{schedule.uid}"
            )
            result_data = result.json()

            if result_data.get("status") == "success":
                update_data = {
                    "active": False,
                    "status": ScheduleStatus.SCHEDULED.value,
                    "last_update": datetime.now(self.timezone).isoformat(),
                    "cron_start": schedule.cron_start if hasattr(schedule, 'cron_start') else None,
                    "cron_stop": schedule.cron_stop if hasattr(schedule, 'cron_stop') else None
                }

                await self.client.put(
                    url=f"{self.api_url}/schedules/{schedule.id}",
                    json=update_data,
                )
                logger.success(
                    f"✅ Workload arrêté avec succès: {schedule.name} (UID: {schedule.uid})"
                )
            else:
                logger.error(
                    f"❌ Échec de l'arrêt du workload {schedule.name} (UID: {schedule.uid}): {result_data.get('message', 'Unknown error')}"
                )

        except Exception as e:
            logger.error(
                f"Erreur lors de l'arrêt du workload {schedule.name} (UID: {schedule.uid}): {e}"
            )
            logger.exception(e)


if __name__ == "__main__":

    async def main():
        # Créer une instance du scheduler
        scheduler = SchedulerEngine(check_interval=60)

        try:
            # Démarrer le scheduler
            await scheduler.start()

            # Garder le programme en cours d'exécution
            while scheduler.running:
                await asyncio.sleep(1)

        except KeyboardInterrupt:
            logger.info("⚠️ Interruption par l'utilisateur (Ctrl+C)")
        except Exception as e:
            logger.error(f"❌ Erreur inattendue: {e}")
            logger.exception(e)
        finally:
            # Arrêter proprement le scheduler
            await scheduler.stop()
            logger.info("👋 Programme terminé")

    # Lancer la boucle d'événements asyncio
    asyncio.run(main())
