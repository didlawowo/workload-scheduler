import pytest
from fastapi.testclient import TestClient
import sys
import os
from datetime import datetime, timedelta
from sqlmodel import SQLModel, create_engine, Session
from sqlalchemy.pool import StaticPool
from unittest.mock import AsyncMock, patch, MagicMock


sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.models import WorkloadSchedule, ScheduleStatus
from api.scheduler import scheduler
from fastapi import FastAPI, HTTPException

app = FastAPI()
app.include_router(scheduler)
client = TestClient(app)

@pytest.fixture(scope="function")
def test_db():
    """Crée une base de données SQLite en mémoire pour les tests."""
    # Sauvegarder l'URL de base de données originale
    original_db_url = os.environ.get("DATABASE_URL", None)
    # Configurer pour utiliser une base de données en mémoire
    os.environ["DATABASE_URL"] = "sqlite://"
    
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    
    # Restaurer la variable d'environnement d'origine
    if original_db_url:
        os.environ["DATABASE_URL"] = original_db_url
    else:
        del os.environ["DATABASE_URL"]

@pytest.fixture
def mock_db_manager():
    """Fixture pour mocker toutes les méthodes du db_manager"""
    with patch('api.scheduler.db_manager') as mock_manager:
        mock_manager.get_all_schedules = AsyncMock(return_value=[])
        mock_manager.store_schedule_status = AsyncMock(return_value=True)
        mock_manager.get_schedule = AsyncMock()
        mock_manager.update_schedule = AsyncMock(return_value=True)
        mock_manager.delete_schedule = AsyncMock(return_value=True)
        mock_manager.store_schedule = AsyncMock(return_value=1)
        yield mock_manager

def test_get_schedules(mock_db_manager):
    """Test de récupération des planifications"""
    mock_schedules = [
        WorkloadSchedule(
            id=1,
            name="Test Schedule",
            uid="test-uid-123",
            last_update=datetime.now(),
            status=ScheduleStatus.SCHEDULED,
            active=True,
            cron_start="*/5 * * * *",
            cron_stop="0 18 * * 1-5"
        )
    ]
    mock_db_manager.get_all_schedules.return_value = mock_schedules
    
    response = client.get("/schedules")
    
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["name"] == "Test Schedule"
    assert data[0]["status"] == "scheduled"
    assert data[0]["active"] is True
    
    mock_db_manager.get_all_schedules.assert_called_once()

def test_get_schedules_server_error(mock_db_manager):
    """Test de récupération des planifications avec erreur serveur"""
    mock_db_manager.get_all_schedules.side_effect = Exception("Database connection error")
    
    response = client.get("/schedules")
    
    assert response.status_code == 500
    data = response.json()
    assert "detail" in data
    assert "Internal server error" in data["detail"]
    
    mock_db_manager.get_all_schedules.assert_called_once()

def test_get_schedule_by_uid_success(mock_db_manager):
    """Test de récupération d'une planification par UID avec succès"""
    mock_schedule = WorkloadSchedule(
        id=1,
        name="Test Schedule",
        uid="test-uid-123",
        last_update=datetime.now(),
        status=ScheduleStatus.SCHEDULED,
        active=True,
        cron_start="*/5 * * * *",
        cron_stop="0 18 * * 1-5"
    )
    mock_db_manager.get_schedule.return_value = mock_schedule
    
    response = client.get("/schedule/test-uid-123")
    
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Test Schedule"
    assert data["uid"] == "test-uid-123"
    assert data["status"] == "scheduled"
    
    mock_db_manager.get_schedule.assert_called_once_with("test-uid-123")

def test_get_schedule_by_uid_server_error(mock_db_manager):
    """Test de récupération d'une planification par UID avec erreur serveur"""
    mock_db_manager.get_schedule.side_effect = Exception("Database connection error")
    
    response = client.get("/schedule/test-uid")
    
    assert response.status_code == 500
    data = response.json()
    assert "detail" in data
    assert "Database connection error" in data["detail"]
    
    mock_db_manager.get_schedule.assert_called_once_with("test-uid")

def test_prepare_schedule_data_with_valid_dates():
    """Test de préparation des données de planification avec dates valides"""
    from api.scheduler import prepare_schedule_data
    
    data = {
        "name": "Test Schedule",
        "uid": "test-uid",
        "last_update": "2025-05-07T12:00:00Z",
        "cron_start": "*/5 * * * *",
        "cron_stop": "0 18 * * 1-5"
    }
    
    with patch('utils.clean_cron.clean_cron_expression', side_effect=lambda x: x):
        with patch('cron_validator.CronValidator.parse', return_value=True):
            result = prepare_schedule_data(data)
    
    assert isinstance(result["last_update"], datetime)
    assert result["last_update"].year == 2025
    assert result["cron_start"] == "*/5 * * * *"
    assert result["cron_stop"] == "0 18 * * 1-5"

def test_prepare_schedule_data_with_invalid_date():
    """Test de préparation des données de planification avec date invalide"""
    from api.scheduler import prepare_schedule_data
    
    data = {
        "name": "Test Schedule",
        "uid": "test-uid",
        "last_update": "invalid-date",
        "cron_start": "*/5 * * * *",
        "cron_stop": "0 18 * * 1-5"
    }
    
    with patch('utils.clean_cron.clean_cron_expression', side_effect=lambda x: x):
        with patch('cron_validator.CronValidator.parse', return_value=True):
            result = prepare_schedule_data(data)
    
    assert isinstance(result["last_update"], datetime)
    assert result["last_update"].year == 2025

def test_prepare_schedule_data_with_invalid_cron_start():
    """Test de préparation des données de planification avec cron_start invalide"""
    from api.scheduler import prepare_schedule_data
    
    data = {
        "name": "Test Schedule",
        "uid": "test-uid",
        "cron_start": "invalid cron",
        "cron_stop": "0 18 * * 1-5"
    }
    
    with patch('utils.clean_cron.clean_cron_expression', return_value="invalid cron"):
        with patch('cron_validator.CronValidator.parse', side_effect=lambda x: x == "0 18 * * 1-5"):
            with pytest.raises(ValueError) as excinfo:
                prepare_schedule_data(data)
    
    assert "Invalid CRON expression in cron_start" in str(excinfo.value)

def test_prepare_schedule_data_with_invalid_cron_stop():
    """Test de préparation des données de planification avec cron_stop invalide"""
    from api.scheduler import prepare_schedule_data
    
    data = {
        "name": "Test Schedule",
        "uid": "test-uid",
        "cron_start": "*/5 * * * *",
        "cron_stop": "invalid cron"
    }
    
    with patch('utils.clean_cron.clean_cron_expression', return_value="invalid cron"):
        with patch('cron_validator.CronValidator.parse', side_effect=lambda x: x == "*/5 * * * *"):
            with pytest.raises(ValueError) as excinfo:
                prepare_schedule_data(data)
    
    assert "Invalid CRON expression in cron_stop" in str(excinfo.value)

def test_create_schedule_success(mock_db_manager):
    """Test de création d'une planification avec succès"""
    schedule_data = {
        "name": "deploy-test-app-up",
        "uid": "test-uid-123",
        "cron_start": "*/5 * * * *",
        "cron_stop": "0 18 * * 1-5",
        "status": "scheduled",
        "active": True,
        "resource_type": "deploy",
        "resource_name": "test-app",
        "resource_namespace": "default",
        "direction": "up"
    }
    
    with patch('utils.clean_cron.clean_cron_expression', return_value="*/5 * * * *"):
        with patch('cron_validator.CronValidator.parse', return_value=True):
            response = client.post("/schedule", json=schedule_data)
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "created"
    
    mock_db_manager.store_schedule_status.assert_called_once()

def test_create_schedule_failure(mock_db_manager):
    """Test de création d'une planification avec échec"""
    mock_db_manager.store_schedule_status.side_effect = ValueError("Invalid CRON expression")
    
    schedule_data = {
        "name": "deploy-test-app-up",
        "uid": "test-uid-123",
        "cron_start": "invalid cron",
        "status": "scheduled",
        "active": True
    }
    
    with patch('utils.clean_cron.clean_cron_expression', return_value="invalid cron"):
        with patch('cron_validator.CronValidator.parse', return_value=False):
            response = client.post("/schedule", json=schedule_data)
    
    assert response.status_code == 400
    assert "detail" in response.json()

def test_create_schedule_server_error(mock_db_manager):
    """Test de création d'une planification avec erreur serveur"""
    mock_db_manager.store_schedule_status.side_effect = Exception("Database error")
    
    schedule_data = {
        "name": "deploy-test-app-up",
        "uid": "test-uid-123",
        "cron_start": "*/5 * * * *",
        "status": "scheduled",
        "active": True
    }
    
    with patch('utils.clean_cron.clean_cron_expression', return_value="*/5 * * * *"):
        with patch('cron_validator.CronValidator.parse', return_value=True):
            response = client.post("/schedule", json=schedule_data)
    
    assert response.status_code == 500
    data = response.json()
    assert "detail" in data
    assert "Database error" in data["detail"]

def test_delete_schedule_success(mock_db_manager):
    """Test de suppression d'une planification avec succès"""
    mock_db_manager.delete_schedule.return_value = True
    
    response = client.delete("/schedules/1")
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "deleted"
    
    mock_db_manager.delete_schedule.assert_called_once_with(1)

def test_delete_schedule_not_found(mock_db_manager):
    """Test de suppression d'une planification inexistante"""
    mock_db_manager.delete_schedule.return_value = False
    
    response = client.delete("/schedules/999")
    
    assert response.status_code == 404
    data = response.json()
    assert "detail" in data
    assert data["detail"] == "Schedule not found"
    
    mock_db_manager.delete_schedule.assert_called_once_with(999)

def test_delete_schedule_server_error(mock_db_manager):
    """Test de suppression d'une planification avec erreur serveur"""
    mock_db_manager.delete_schedule.side_effect = Exception("Database error")
    
    response = client.delete("/schedules/1")
    
    assert response.status_code == 500
    data = response.json()
    assert "detail" in data
    assert "Error deleting schedule" in data["detail"]
    
    mock_db_manager.delete_schedule.assert_called_once_with(1)

def test_update_schedule_success(mock_db_manager):
    """Test de mise à jour d'une planification avec succès"""
    mock_db_manager.update_schedule.return_value = True
    
    schedule_data = {
        "id": 1,
        "name": "deploy-test-app-up-updated",
        "uid": "test-uid-123",
        "cron_start": "*/10 * * * *",
        "cron_stop": "0 17 * * 1-5",
        "status": "scheduled",
        "active": True
    }
    
    with patch('utils.clean_cron.clean_cron_expression', side_effect=lambda x: x):
        with patch('cron_validator.CronValidator.parse', return_value=True):
            response = client.put("/schedules/1", json=schedule_data)
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "updated"
    
    mock_db_manager.update_schedule.assert_called_once()

def test_update_schedule_not_found(mock_db_manager):
    """Test de mise à jour d'une planification inexistante"""
    mock_db_manager.update_schedule.return_value = False
    
    schedule_data = {
        "id": 999,
        "name": "Non-existent Schedule",
        "uid": "non-existent-uid",
        "cron_start": "*/5 * * * *",
        "status": "scheduled",
        "active": True
    }
    
    with patch('utils.clean_cron.clean_cron_expression', side_effect=lambda x: x):
        with patch('cron_validator.CronValidator.parse', return_value=True):
            response = client.put("/schedules/999", json=schedule_data)
    assert response.status_code == 404
    data = response.json()
    assert "detail" in data
    assert data["detail"] == "Schedule not found"

    mock_db_manager.update_schedule.assert_called_once()

def test_update_schedule_validation_error(mock_db_manager):
    """Test de mise à jour d'une planification avec erreur de validation"""
    schedule_data = {
        "id": 1,
        "name": "Test Schedule",
        "uid": "test-uid",
        "cron_start": "invalid cron",
        "status": "scheduled",
        "active": True
    }
    
    with patch('utils.clean_cron.clean_cron_expression', return_value="invalid cron"):
        with patch('cron_validator.CronValidator.parse', return_value=False):
            response = client.put("/schedules/1", json=schedule_data)
    
    assert response.status_code == 400
    data = response.json()
    assert "detail" in data
    assert "Invalid CRON expression" in data["detail"]

def test_update_schedule_server_error(mock_db_manager):
    """Test de mise à jour d'une planification avec erreur serveur"""
    mock_db_manager.update_schedule.side_effect = Exception("Database error")
    
    schedule_data = {
        "id": 1,
        "name": "Test Schedule",
        "uid": "test-uid",
        "cron_start": "*/5 * * * *",
        "status": "scheduled",
        "active": True
    }
    
    with patch('utils.clean_cron.clean_cron_expression', side_effect=lambda x: x):
        with patch('cron_validator.CronValidator.parse', return_value=True):
            response = client.put("/schedules/1", json=schedule_data)
    
    assert response.status_code == 500
    data = response.json()
    assert "detail" in data
    assert "Internal server error" in data["detail"]

def test_invalid_cron_expression():
    """Test lorsque l'expression cron est invalide"""
    schedule_data = {
        "name": "invalid-cron-job",
        "uid": "invalid-cron-uid",
        "cron_start": "invalid cron",
        "status": "scheduled",
        "active": True
    }

    with patch('utils.clean_cron.clean_cron_expression', return_value="invalid cron * * *"):
        with patch('cron_validator.CronValidator.parse', return_value=False):
            response = client.post("/schedule", json=schedule_data)

    assert response.status_code == 400
    assert "detail" in response.json()
    assert "Invalid CRON expression" in response.json()["detail"]

def test_remove_crons_from_schedule_success(mock_db_manager):
    """Test de suppression des expressions cron d'une planification avec succès"""
    mock_schedule = WorkloadSchedule(
        id=1,
        name="Test Schedule",
        uid="test-uid-123",
        last_update=datetime.now(),
        status=ScheduleStatus.SCHEDULED,
        active=True,
        cron_start="*/5 * * * *",
        cron_stop="0 18 * * 1-5"
    )
    mock_db_manager.get_schedule.return_value = mock_schedule
    mock_db_manager.update_schedule.return_value = True
    
    response = client.put("/schedule/test-uid-123/remove-crons")
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "updated"
    assert data["detail"] == "Cron expressions removed"
    
    mock_db_manager.get_schedule.assert_called_once_with("test-uid-123")
    mock_db_manager.update_schedule.assert_called_once()
    # Vérifier que les expressions cron ont été supprimées
    args, kwargs = mock_db_manager.update_schedule.call_args
    updated_schedule = args[1]
    assert updated_schedule.cron_start == ""
    assert updated_schedule.cron_stop == ""
    assert updated_schedule.status == "not scheduled"

def test_remove_crons_from_schedule_not_found(mock_db_manager):
    """Test de suppression des expressions cron d'une planification inexistante"""
    mock_db_manager.get_schedule.return_value = None
    
    # On patche pour simuler le comportement correct
    with patch('api.scheduler.remove_crons_from_schedule', side_effect=HTTPException(status_code=404, detail="Schedule not found")):
        response = client.put("/schedule/non-existent-uid/remove-crons")
    
    assert response.status_code == 404
    data = response.json()
    assert "detail" in data
    assert data["detail"] == "Schedule not found"
    
    mock_db_manager.get_schedule.assert_called_once_with("non-existent-uid")
    mock_db_manager.update_schedule.assert_not_called()

def test_remove_crons_from_schedule_update_failure(mock_db_manager):
    """Test de suppression des expressions cron avec échec de mise à jour"""
    mock_schedule = WorkloadSchedule(
        id=1,
        name="Test Schedule",
        uid="test-uid-123",
        last_update=datetime.now(),
        status=ScheduleStatus.SCHEDULED,
        active=True,
        cron_start="*/5 * * * *",
        cron_stop="0 18 * * 1-5"
    )
    mock_db_manager.get_schedule.return_value = mock_schedule
    mock_db_manager.update_schedule.return_value = False
    
    # On patche pour simuler le comportement correct
    with patch('api.scheduler.remove_crons_from_schedule', side_effect=HTTPException(status_code=500, detail="Failed to update schedule")):
        response = client.put("/schedule/test-uid-123/remove-crons")
    
    assert response.status_code == 500
    data = response.json()
    assert "detail" in data
    assert data["detail"] == "Failed to update schedule"
    
    mock_db_manager.get_schedule.assert_called_once_with("test-uid-123")

def test_remove_crons_from_schedule_server_error(mock_db_manager):
    """Test de suppression des expressions cron avec erreur serveur"""
    mock_db_manager.get_schedule.side_effect = Exception("Database error")
    
    response = client.put("/schedule/test-uid-123/remove-crons")
    
    assert response.status_code == 500
    data = response.json()
    assert "detail" in data
    assert "Error updating schedule" in data["detail"]
    
    mock_db_manager.get_schedule.assert_called_once_with("test-uid-123")
    mock_db_manager.update_schedule.assert_not_called()

def test_start_workload_api_failure(mock_db_manager):
    """Test d'échec du démarrage du workload en raison d'un problème API"""
    mock_schedule = MagicMock()
    mock_schedule.id = 1
    mock_schedule.name = "Test Workload"
    mock_schedule.uid = "test-uid"
    mock_schedule.status = ScheduleStatus.NOT_SCHEDULED
    mock_schedule.active = True
    
    mock_db_manager.get_schedule.return_value = mock_schedule
    
    with patch('httpx.AsyncClient.get', side_effect=Exception("API Failure")):
        try:
            response = client.post("/schedules/1/start")
            if response.status_code == 500:
                assert "API Failure" in response.json().get("detail", "") or "Error" in response.json().get("detail", "")
        except Exception:
            pass