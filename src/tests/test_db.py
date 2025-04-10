"""
Script de test pour vérifier le bon fonctionnement de la base de données du Workload Scheduler.
Ce script teste les opérations CRUD sur les planifications de charges de travail.
"""

import sys
import os
from datetime import datetime, timedelta
from loguru import logger

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.init_db import init_db
from core.models import WorkloadSchedule
from core.db import add_schedule, get_all_schedules, delete_schedule

def setup():
    """Initialise la base de données pour les tests."""
    logger.info("Initialisation de la base de données pour les tests...")
    init_db()
    logger.success("Base de données initialisée avec succès.")

def test_add_schedule():
    """Teste l'ajout d'une planification dans la base de données."""
    logger.info("Test: Ajout d'une planification")
    
    now = datetime.now()
    test_schedule = WorkloadSchedule(
        name="Test Schedule 1",
        start_time=now,
        end_time=now + timedelta(hours=2),
        status="scheduled",
        active=True
    )
    
    add_schedule(test_schedule)
    
    schedules = get_all_schedules()
    assert len(schedules) > 0, "La planification n'a pas été ajoutée à la base de données"
    
    logger.success("Planification ajoutée avec succès")
    return schedules[0].id

def test_get_all_schedules():
    """Teste la récupération de toutes les planifications."""
    logger.info("Test: Récupération de toutes les planifications")
    
    now = datetime.now()
    test_schedule = WorkloadSchedule(
        name="Test Schedule 2",
        start_time=now + timedelta(hours=3),
        end_time=now + timedelta(hours=5),
        status="scheduled",
        active=True
    )
    add_schedule(test_schedule)
    
    schedules = get_all_schedules()
    
    assert len(schedules) >= 2, "Impossible de récupérer toutes les planifications"
    
    logger.success(f"Récupération réussie - {len(schedules)} planifications trouvées")
    
    for schedule in schedules:
        logger.info(f"ID: {schedule.id}, Nom: {schedule.name}, Début: {schedule.start_time}, Fin: {schedule.end_time}")
    
    return schedules

def test_delete_schedule(schedule_id):
    """Teste la suppression d'une planification."""
    logger.info(f"Test: Suppression de la planification avec ID {schedule_id}")
    
    success = delete_schedule(schedule_id)
    
    assert success, f"Échec de la suppression de la planification avec ID {schedule_id}"
    
    schedules = get_all_schedules()
    for schedule in schedules:
        assert schedule.id != schedule_id, f"La planification avec ID {schedule_id} existe toujours après suppression"
    
    logger.success(f"Planification avec ID {schedule_id} supprimée avec succès")

def run_tests():
    """Exécute tous les tests de base de données."""
    try:
        setup()
        
        schedule_id = test_add_schedule()
        schedules = test_get_all_schedules()
        test_delete_schedule(schedule_id)
        
        logger.info("Nettoyage des données de test...")
        for schedule in schedules:
            if schedule.id != schedule_id:
                delete_schedule(schedule.id)
        
        logger.success("Tous les tests ont réussi!")
        return True
    
    except AssertionError as e:
        logger.error(f"Échec du test: {str(e)}")
        return False
    except Exception as e:
        logger.error(f"Erreur inattendue: {str(e)}")
        return False

if __name__ == "__main__":
    logger.info("Démarrage des tests de base de données pour Workload Scheduler")
    success = run_tests()
    if success:
        sys.exit(0)
    else:
        sys.exit(1)