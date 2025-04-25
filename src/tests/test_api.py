import pytest
from fastapi.testclient import TestClient
import sys
import os
from datetime import datetime
from sqlmodel import SQLModel, create_engine, Session
from sqlalchemy.pool import StaticPool
from unittest.mock import AsyncMock, patch

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.models import WorkloadSchedule, ScheduleStatus
from api.scheduler import scheduler
from fastapi import FastAPI

app = FastAPI()
app.include_router(scheduler)
client = TestClient(app)

@pytest.fixture(scope="function")
def test_db():
    """Crée une base de données SQLite en mémoire pour les tests."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    
    with Session(engine) as session:
        yield session

@pytest.fixture
def mock_db_manager():
    """Fixture pour mocker toutes les méthodes du db_manager"""
    with patch('api.scheduler.db_manager') as mock_manager:
        mock_manager.get_all_schedules = AsyncMock()
        mock_manager.store_schedule_status = AsyncMock()
        mock_manager.get_schedule = AsyncMock()
        mock_manager.update_schedule = AsyncMock()
        mock_manager.delete_schedule = AsyncMock()
        
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
            response = client.post("/schedules", json=schedule_data)
    
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
            response = client.post("/schedules", json=schedule_data)
    
    assert response.status_code == 400
    assert "detail" in response.json()

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
