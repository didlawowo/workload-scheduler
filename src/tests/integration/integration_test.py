import pytest
from fastapi.testclient import TestClient
import sys
import os
from datetime import datetime
from sqlmodel import SQLModel, create_engine, Session
from sqlalchemy.pool import StaticPool
from unittest.mock import AsyncMock

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

@pytest.mark.asyncio
async def test_integration_workflow(test_db, monkeypatch):
    """Test d'intégration du workflow complet"""
    async_mock_store_schedule = AsyncMock()
    async_mock_get_all_schedules = AsyncMock()
    async_mock_delete_schedule = AsyncMock()
    
    async def mock_store_schedule_status(data):
        schedule = WorkloadSchedule(
            id=1,
            name=data["name"],
            uid=data.get("uid", "test-uid"),
            last_update=datetime.utcnow(),
            status=ScheduleStatus.SCHEDULED,
            active=data.get("active", True),
            cron_start=data.get("cron_start"),
            cron_stop=data.get("cron_stop")
        )
        test_db.add(schedule)
        test_db.commit()
        return schedule
    
    async def mock_get_all_schedules():
        return test_db.query(WorkloadSchedule).all()
    
    async def mock_delete_schedule(schedule_id):
        schedule = test_db.get(WorkloadSchedule, schedule_id)
        if not schedule:
            return False
        test_db.delete(schedule)
        test_db.commit()
        return True
    
    async def mock_get_schedule(uid):
        result = test_db.query(WorkloadSchedule).filter(WorkloadSchedule.uid == uid).first()
        return result
    
    async_mock_store_schedule.side_effect = mock_store_schedule_status
    async_mock_get_all_schedules.side_effect = mock_get_all_schedules
    async_mock_delete_schedule.side_effect = mock_delete_schedule
    
    monkeypatch.setattr("api.scheduler.db_manager.store_schedule_status", async_mock_store_schedule)
    monkeypatch.setattr("api.scheduler.db_manager.get_all_schedules", async_mock_get_all_schedules)
    monkeypatch.setattr("api.scheduler.db_manager.delete_schedule", async_mock_delete_schedule)
    monkeypatch.setattr("api.scheduler.db_manager.get_schedule", AsyncMock(side_effect=mock_get_schedule))
    
    schedule_data = {
        "name": "deploy-test-app-up",
        "uid": "integration-test-uid",
        "cron_start": "*/5 * * * *",
        "cron_stop": "0 18 * * 1-5",
        "status": "scheduled",
        "active": True,
        "resource_type": "deploy",
        "resource_name": "test-app",
        "resource_namespace": "default",
        "direction": "up"
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
        if schedule["name"] == "deploy-test-app-up" and schedule["uid"] == "integration-test-uid":
            schedule_id = schedule["id"]
            break
    
    assert schedule_id is not None, "Le schedule créé n'a pas pu être trouvé dans la liste"
    
    response = client.delete(f"/schedules/{schedule_id}")
    assert response.status_code == 200
    assert response.json()["status"] == "deleted"
    
    response = client.get("/schedules")
    schedules = response.json()
    for schedule in schedules:
        assert schedule["id"] != schedule_id, f"Le schedule {schedule_id} existe toujours après suppression"
