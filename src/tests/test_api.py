"""
Script de test pour vérifier le bon fonctionnement de l'API REST du Workload Scheduler.
Ce script envoie des requêtes HTTP pour tester les endpoints de l'API.
"""

import requests
import json
from datetime import datetime, timedelta
import sys
from loguru import logger

BASE_URL = "http://localhost:8000"

def test_create_schedule():
    """Teste la création d'une planification via l'API."""
    logger.info("Test: Création d'une planification via POST /schedules")
    
    now = datetime.now()
    schedule_data = {
        "name": "API Test Schedule",
        "start_time": (now + timedelta(minutes=30)).isoformat(),
        "end_time": (now + timedelta(hours=2)).isoformat(),
        "status": "scheduled",
        "active": True
    }
    
    response = requests.post(f"{BASE_URL}/schedules", json=schedule_data)
    
    assert response.status_code == 200, f"Échec de la création: {response.status_code} - {response.text}"
    assert response.json().get("status") == "created", "La réponse ne contient pas le statut 'created'"
    
    logger.success("Création de planification réussie")
    return schedule_data

def test_get_schedules():
    """Teste la récupération des planifications via l'API."""
    logger.info("Test: Récupération des planifications via GET /schedules")
    
    response = requests.get(f"{BASE_URL}/schedules")
    
    assert response.status_code == 200, f"Échec de la récupération: {response.status_code} - {response.text}"
    
    schedules = response.json()
    assert isinstance(schedules, list), "La réponse n'est pas une liste"
    assert len(schedules) > 0, "Aucune planification trouvée"
    
    logger.success(f"Récupération réussie - {len(schedules)} planifications trouvées")
    
    for schedule in schedules:
        logger.info(f"ID: {schedule['id']}, Nom: {schedule['name']}")
    
    return schedules

def test_delete_schedule(schedule_id):
    """Teste la suppression d'une planification via l'API."""
    logger.info(f"Test: Suppression de la planification avec ID {schedule_id}")
    
    response = requests.delete(f"{BASE_URL}/schedules/{schedule_id}")
    
    assert response.status_code == 200, f"Échec de la suppression: {response.status_code} - {response.text}"
    assert response.json().get("status") == "deleted", "La réponse ne contient pas le statut 'deleted'"
    
    logger.success(f"Suppression de la planification avec ID {schedule_id} réussie")
    
    response = requests.get(f"{BASE_URL}/schedules")
    schedules = response.json()
    for schedule in schedules:
        assert schedule['id'] != schedule_id, f"La planification avec ID {schedule_id} existe toujours après suppression"

def run_api_tests():
    """Exécute tous les tests d'API."""
    try:
        test_create_schedule()
        schedules = test_get_schedules()
        
        if schedules:
            test_delete_schedule(schedules[0]['id'])
        
        logger.success("Tous les tests d'API ont réussi!")
        return True
    
    except AssertionError as e:
        logger.error(f"Échec du test: {str(e)}")
        return False
    except requests.exceptions.ConnectionError:
        logger.error(f"Erreur de connexion: Assurez-vous que le serveur est en cours d'exécution sur {BASE_URL}")
        return False
    except Exception as e:
        logger.error(f"Erreur inattendue: {str(e)}")
        return False

if __name__ == "__main__":
    logger.info("Démarrage des tests d'API pour Workload Scheduler")
    success = run_api_tests()
    if success:
        sys.exit(0)
    else:
        sys.exit(1)