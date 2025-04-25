import asyncio
from datetime import datetime
import pytz
from loguru import logger
from croniter import croniter
from core.models import WorkloadSchedule, ScheduleStatus
from utils.helpers import RetryableAsyncClient
import os
from icecream import ic
from types import SimpleNamespace

class SchedulerEngine:
    """
    Moteur de scheduling qui vérifie les expressions cron pour démarrer/arrêter les workloads.
    
    Attributes:
        check_interval: Intervalle (en secondes) entre chaque vérification des programmations
        running: Indicateur si le scheduleur est en cours d'exécution
        _task: Tâche asyncio pour le processus en arrière-plan
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
        self.timezone = pytz.timezone('Europe/Paris') # TODO faire une variable d'env
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
        logger.info(f"⏰ Démarrage du moteur de scheduling (intervalle: {self.check_interval}s)")
        
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
            schedules = await self.client.get(url=f"{os.getenv('API_URL')}/schedules")
            ic(schedules.json)
            ic(schedules.content)
            schedules_dict = schedules.json()
            ic(schedules_dict)
            logger.info(f"Vérification de {len(schedules_dict)} programmations à {datetime.now(self.timezone).strftime('%H:%M:%S')}")
            
            if not schedules_dict:
                logger.info("Aucune programmation trouvée dans la base de données")
                return
            schedule_object = [SimpleNamespace(**item) for item in schedules_dict]
            ic(schedule_object[0])
            for schedule in schedule_object:
                logger.debug(f"ID= {schedule.id}, "
                           f"Nom= {schedule.name}, "
                           f"UID= {schedule.uid}, "
                           f"Status= {schedule.status}, "
                           f"Active= {schedule.active}, "
                           f"Start= {schedule.cron_start}, "
                           f"Stop= {schedule.cron_stop}")
            
            now = datetime.now(self.timezone)
            
            for schedule in schedule_object:
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
        ic(schedule.id)
        try:
            if not schedule.active:
                logger.debug(f"Programmation {schedule.id} ({schedule.name}, UID: {schedule.uid}) inactive, ignorée")
                return
                
            should_start = self._should_execute(schedule.cron_start, now)
            should_stop = self._should_execute(schedule.cron_stop, now)
            
            logger.debug(f"Programmation {schedule.id} ({schedule.name}, UID: {schedule.uid}): status={schedule.status}, should_start={should_start}, should_stop={should_stop}")
            logger.debug(f"cron_start: {schedule.cron_start}, cron_stop: {schedule.cron_stop}")
            
            if should_start and schedule.status == ScheduleStatus.NOT_SCHEDULED:
                logger.info(f"Déclenchement du démarrage pour {schedule.name} (ID: {schedule.id}, UID: {schedule.uid})")
                # await self._start_workload(schedule)
            elif should_stop and schedule.status == ScheduleStatus.SCHEDULED:
                logger.info(f"Déclenchement de l'arrêt pour {schedule.name} (ID: {schedule.id}, UID: {schedule.uid})")
                # await self._stop_workload(schedule)
            else:
                conditions = []
                if schedule.status == ScheduleStatus.NOT_SCHEDULED and not should_start:
                    conditions.append("Le workload est arrêté mais l'heure de démarrage n'est pas atteinte")
                elif schedule.status == ScheduleStatus.SCHEDULED and not should_stop:
                    conditions.append("Le workload est démarré mais l'heure d'arrêt n'est pas atteinte")
                elif schedule.status == ScheduleStatus.NOT_SCHEDULED and should_stop:
                    conditions.append("Le workload est déjà arrêté")
                elif schedule.status == ScheduleStatus.SCHEDULED and should_start:
                    conditions.append("Le workload est déjà démarré")
                
                logger.debug(f"Aucune action pour {schedule.name} (UID: {schedule.uid}): {', '.join(conditions)}")
                
        except Exception as e:
            logger.error(f"Erreur lors du traitement de la programmation {schedule.id}: {e}")
            logger.exception(e)
            
    def _should_execute(self, cron_expression: str, now: datetime) -> bool:
        """
        Vérifie si une expression cron doit être exécutée.
        
        Args:
            cron_expression: L'expression cron à vérifier
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
            
            logger.debug(f"Expression cron '{cron_expression}': "
                        f"précédente={prev_dt}, "
                        f"actuelle={now}, "
                        f"prochaine={next_dt}, "
                        f"delta={delta}s, "
                        f"intervalle={self.check_interval}s")
            return (0 <= delta < self.check_interval) or (0 <= next_delta < self.check_interval)
            
        except Exception as e:
            logger.error(f"Erreur lors du parsing de l'expression cron '{cron_expression}': {e}")
            return False
            
    async def _start_workload(self, schedule: WorkloadSchedule):
        """
        Démarre un workload en utilisant son UID.
        
        Args:
            schedule: La programmation du workload à démarrer
        """
        try:
            logger.info(f"🚀 Démarrage du workload: {schedule.name} (ID: {schedule.id}, UID: {schedule.uid})")

            result = await self.client.get(url=f"{os.getenv('API_URL')}/up/{schedule.uid}")
            # TODO faire call api
            ic(result)
            
            if result["status"] == "success":
                updated_schedule = schedule
                updated_schedule.status = ScheduleStatus.SCHEDULED
                updated_schedule.last_update = datetime.now(self.timezone)
                self.client.put(url=f"{os.getenv('API_URL')}/schedules/{schedule.id}")
                logger.success(f"✅ Workload démarré avec succès: {schedule.name} (UID: {schedule.uid})")
            else:
                logger.error(f"❌ Échec du démarrage du workload {schedule.name} (UID: {schedule.uid}): {result['message']}")
                
        except Exception as e:
            logger.error(f"Erreur lors du démarrage du workload {schedule.name} (UID: {schedule.uid}): {e}")
            logger.exception(e)
            
    async def _stop_workload(self, schedule: WorkloadSchedule):
        """
        Arrête un workload en utilisant son UID.
        
        Args:
            schedule: La programmation du workload à arrêter
        """
        try:
            logger.info(f"🛑 Arrêt du workload: {schedule.name} (ID: {schedule.id}, UID: {schedule.uid})")
             # TODO faire un call a l'api
            result = "toto"
            
            if result["status"] == "success":
                updated_schedule = schedule
                updated_schedule.status = ScheduleStatus.NOT_SCHEDULED
                updated_schedule.last_update = datetime.now(self.timezone)
                
                self.client.put(url=f"{os.getenv('API_URL')}/schedules/{schedule.id}")
                logger.success(f"✅ Workload arrêté avec succès: {schedule.name} (UID: {schedule.uid})")
            else:
                logger.error(f"❌ Échec de l'arrêt du workload {schedule.name} (UID: {schedule.uid}): {result['message']}")
                
        except Exception as e:
            logger.error(f"Erreur lors de l'arrêt du workload {schedule.name} (UID: {schedule.uid}): {e}")
            logger.exception(e)
    
if __name__ == "__main__":
        SchedulerEngine(check_interval=60)
