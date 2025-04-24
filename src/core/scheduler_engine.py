import asyncio
from datetime import datetime
import pytz
from loguru import logger
from croniter import croniter
from core.dbManager import DatabaseManager
from core.models import WorkloadSchedule, ScheduleStatus
from utils.helpers import apps_v1
from api.workload import scale_up_app, shutdown_app

class SchedulerEngine:
    """
    Moteur de scheduling qui vérifie les expressions cron pour démarrer/arrêter les workloads.
    
    Attributes:
        db_manager: Gestionnaire de base de données pour récupérer et mettre à jour les programmations
        check_interval: Intervalle (en secondes) entre chaque vérification des programmations
        running: Indicateur si le scheduleur est en cours d'exécution
        _task: Tâche asyncio pour le processus en arrière-plan
    """
    
    def __init__(self, db_manager: DatabaseManager, check_interval: int = 60):
        """
        Initialise le moteur de scheduling.
        
        Args:
            db_manager: Gestionnaire de base de données
            check_interval: Intervalle de vérification en secondes (par défaut: 60)
        """
        self.db_manager = db_manager
        self.check_interval = check_interval
        self.running = False
        self._task = None
        self.timezone = pytz.timezone('Europe/Paris')
        
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
            schedules = await self.db_manager.get_all_schedules()
            logger.info(f"Vérification de {len(schedules)} programmations à {datetime.now(self.timezone).strftime('%H:%M:%S')}")
            
            if not schedules:
                logger.warning("Aucune programmation trouvée dans la base de données")
                return
                
            for idx, schedule in enumerate(schedules):
                logger.debug(f"Programmation {idx+1}/{len(schedules)}: "
                           f"ID={schedule.id}, "
                           f"Nom={schedule.name}, "
                           f"UID={schedule.uid}, "
                           f"Status={schedule.status}, "
                           f"Active={schedule.active}, "
                           f"Start={schedule.cron_start}, "
                           f"Stop={schedule.cron_stop}")
            
            now = datetime.now(self.timezone)
            
            for schedule in schedules:
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
            if not schedule.active:
                logger.debug(f"Programmation {schedule.id} ({schedule.name}, UID: {schedule.uid}) inactive, ignorée")
                return
                
            should_start = self._should_execute(schedule.cron_start, now)
            should_stop = self._should_execute(schedule.cron_stop, now)
            
            logger.debug(f"Programmation {schedule.id} ({schedule.name}, UID: {schedule.uid}): status={schedule.status}, should_start={should_start}, should_stop={should_stop}")
            logger.debug(f"cron_start: {schedule.cron_start}, cron_stop: {schedule.cron_stop}")
            
            if should_start and schedule.status == ScheduleStatus.NOT_SCHEDULED:
                logger.info(f"Déclenchement du démarrage pour {schedule.name} (ID: {schedule.id}, UID: {schedule.uid})")
                await self._start_workload(schedule)
            elif should_stop and schedule.status == ScheduleStatus.SCHEDULED:
                logger.info(f"Déclenchement de l'arrêt pour {schedule.name} (ID: {schedule.id}, UID: {schedule.uid})")
                await self._stop_workload(schedule)
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
            resource_info = await self._get_resource_info_by_uid(schedule.uid)
            
            if not resource_info:
                logger.error(f"❌ Workload non trouvé avec l'UID: {schedule.uid}")
                return
                
            namespace = resource_info["namespace"]
            resource_type = resource_info["type"]
            name = resource_info["name"]
            logger.info(f"Informations workload trouvées: {resource_type}/{namespace}/{name}")
            result = await scale_up_app(resource_type, namespace, name)
            
            if result["status"] == "success":
                updated_schedule = schedule
                updated_schedule.status = ScheduleStatus.SCHEDULED
                updated_schedule.last_update = datetime.now(self.timezone)
                
                await self.db_manager.update_schedule(schedule.id, updated_schedule)
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
            resource_info = await self._get_resource_info_by_uid(schedule.uid)
            
            if not resource_info:
                logger.error(f"❌ Workload non trouvé avec l'UID: {schedule.uid}")
                return
                
            namespace = resource_info["namespace"]
            resource_type = resource_info["type"]
            name = resource_info["name"]
            logger.info(f"Informations workload trouvées: {resource_type}/{namespace}/{name}")
            result = await shutdown_app(resource_type, namespace, name)
            
            if result["status"] == "success":
                updated_schedule = schedule
                updated_schedule.status = ScheduleStatus.NOT_SCHEDULED
                updated_schedule.last_update = datetime.now(self.timezone)
                
                await self.db_manager.update_schedule(schedule.id, updated_schedule)
                logger.success(f"✅ Workload arrêté avec succès: {schedule.name} (UID: {schedule.uid})")
            else:
                logger.error(f"❌ Échec de l'arrêt du workload {schedule.name} (UID: {schedule.uid}): {result['message']}")
                
        except Exception as e:
            logger.error(f"Erreur lors de l'arrêt du workload {schedule.name} (UID: {schedule.uid}): {e}")
            logger.exception(e)
    
    async def _get_resource_info_by_uid(self, uid: str):
        """
        Récupère les informations d'un workload à partir de son UID.
        
        Args:
            uid: L'UID du workload à rechercher
        Returns:
            Un dictionnaire contenant les informations du workload ou None si non trouvé
        """
        try:
            deployments = apps_v1.list_deployment_for_all_namespaces(watch=False)
            for deploy in deployments.items:
                if deploy.metadata.uid == uid:
                    return {
                        "type": "deploy",
                        "namespace": deploy.metadata.namespace,
                        "name": deploy.metadata.name
                    }
            
            statefulsets = apps_v1.list_stateful_set_for_all_namespaces(watch=False)
            for sts in statefulsets.items:
                if sts.metadata.uid == uid:
                    return {
                        "type": "sts",
                        "namespace": sts.metadata.namespace,
                        "name": sts.metadata.name
                    }
            
            daemonsets = apps_v1.list_daemon_set_for_all_namespaces(watch=False)
            for ds in daemonsets.items:
                if ds.metadata.uid == uid:
                    return {
                        "type": "ds",
                        "namespace": ds.metadata.namespace,
                        "name": ds.metadata.name
                    }
            
            logger.warning(f"Aucun workload trouvé avec l'UID: {uid}")
            return None
            
        except Exception as e:
            logger.error(f"Erreur lors de la recherche du workload avec l'UID {uid}: {e}")
            logger.exception(e)
            return None