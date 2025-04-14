import pytest
from fastapi.testclient import TestClient
import sys
import os
from datetime import datetime
from sqlmodel import SQLModel, create_engine, Session
from sqlalchemy.pool import StaticPool

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.models import WorkloadSchedule
from api.scheduler import router
from fastapi import FastAPI

app = FastAPI()
app.include_router(router)
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
def monkeypatch_get_all_schedules(monkeypatch):
    """Fixture pour monkeypatcher get_all_schedules"""
    def mock_get_all_schedules():
        return [
            WorkloadSchedule(
                id=1, 
                name="Test Schedule", 
                start_time=datetime.now(), 
                end_time=datetime.now(), 
                status="scheduled", 
                active=True
            )
        ]
    monkeypatch.setattr("api.routes.get_all_schedules", mock_get_all_schedules)

@pytest.fixture
def monkeypatch_add_schedule(monkeypatch):
    """Fixture pour monkeypatcher add_schedule"""
    def mock_add_schedule(schedule):
        return
    monkeypatch.setattr("api.routes.add_schedule", mock_add_schedule)

@pytest.fixture
def monkeypatch_add_schedule_fail(monkeypatch):
    """Fixture pour monkeypatcher add_schedule avec échec"""
    def mock_add_schedule_fail(schedule):
        raise Exception("DB Error")
    monkeypatch.setattr("api.routes.add_schedule", mock_add_schedule_fail)

@pytest.fixture
def monkeypatch_delete_schedule_success(monkeypatch):
    """Fixture pour monkeypatcher delete_schedule avec succès"""
    def mock_delete_schedule(schedule_id):
        return True
    monkeypatch.setattr("api.routes.delete_schedule", mock_delete_schedule)

@pytest.fixture
def monkeypatch_delete_schedule_fail(monkeypatch):
    """Fixture pour monkeypatcher delete_schedule avec échec"""
    def mock_delete_schedule(schedule_id):
        return False
    monkeypatch.setattr("api.routes.delete_schedule", mock_delete_schedule)

@pytest.fixture
def monkeypatch_update_schedule_success(monkeypatch):
    """Fixture pour monkeypatcher update_schedule avec succès"""
    def mock_update_schedule(schedule_id, schedule):
        return True
    monkeypatch.setattr("api.routes.update_schedule", mock_update_schedule)

@pytest.fixture
def monkeypatch_update_schedule_fail(monkeypatch):
    """Fixture pour monkeypatcher update_schedule avec échec"""
    def mock_update_schedule(schedule_id, schedule):
        return False
    monkeypatch.setattr("api.routes.update_schedule", mock_update_schedule)

def test_get_schedules(monkeypatch_get_all_schedules):
    """Test de récupération des planifications"""
    response = client.get("/schedules")
    
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["name"] == "Test Schedule"
    assert data[0]["status"] == "scheduled"
    assert data[0]["active"] == True

def test_create_schedule_success(monkeypatch_add_schedule):
    """Test de création d'une planification avec succès"""
    schedule_data = {
        "name": "New Schedule",
        "start_time": datetime.now().isoformat(),
        "end_time": datetime.now().isoformat(),
        "status": "scheduled",
        "active": True
    }
    
    response = client.post("/schedules", json=schedule_data)
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "created"

def test_create_schedule_failure(monkeypatch_add_schedule_fail):
    """Test de création d'une planification avec échec"""
    schedule_data = {
        "name": "New Schedule",
        "start_time": datetime.now().isoformat(),
        "end_time": datetime.now().isoformat(),
        "status": "scheduled",
        "active": True
    }
    
    response = client.post("/schedules", json=schedule_data)
    
    assert response.status_code == 400
    assert "detail" in response.json()

def test_delete_schedule_success(monkeypatch_delete_schedule_success):
    """Test de suppression d'une planification avec succès"""
    response = client.delete("/schedules/1")
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "deleted"

def test_delete_schedule_not_found(monkeypatch_delete_schedule_fail):
    """Test de suppression d'une planification inexistante"""
    response = client.delete("/schedules/999")
    
    assert response.status_code == 404
    data = response.json()
    assert "detail" in data
    assert data["detail"] == "Schedule not found"

def test_integration_workflow(test_db, monkeypatch):
    """Test d'intégration du workflow complet"""
    def mock_add_schedule(schedule):
        test_db.add(schedule)
        test_db.commit()
    
    def mock_get_all_schedules():
        return test_db.query(WorkloadSchedule).all()
    
    def mock_delete_schedule(schedule_id):
        schedule = test_db.get(WorkloadSchedule, schedule_id)
        if not schedule:
            return False
        test_db.delete(schedule)
        test_db.commit()
        return True
        
    monkeypatch.setattr("api.routes.add_schedule", mock_add_schedule)
    monkeypatch.setattr("api.routes.get_all_schedules", mock_get_all_schedules)
    monkeypatch.setattr("api.routes.delete_schedule", mock_delete_schedule)
    
    schedule_data = {
        "name": "Integration Test Schedule",
        "start_time": datetime.now().isoformat(),
        "end_time": datetime.now().isoformat(),
        "status": "scheduled",
        "active": True
    }
    
    response = client.post("/schedules", json=schedule_data)
    assert response.status_code == 200
    assert response.json()["status"] == "created"
    
    response = client.get("/schedules")
    assert response.status_code == 200
    schedules = response.json()
    assert len(schedules) >= 1
    
    schedule_id = None
    for schedule in schedules:
        if schedule["name"] == "Integration Test Schedule":
            schedule_id = schedule["id"]
            break
    
    assert schedule_id is not None
    
    response = client.delete(f"/schedules/{schedule_id}")
    assert response.status_code == 200
    assert response.json()["status"] == "deleted"
    
    response = client.get("/schedules")
    schedules = response.json()
    for schedule in schedules:
        assert schedule["id"] != schedule_id