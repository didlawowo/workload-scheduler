import pytest
import sys
import os
from datetime import datetime
import uuid
from unittest.mock import patch, AsyncMock
from loguru import logger

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.dbManager import DatabaseManager
from core.models import WorkloadSchedule

pytestmark = pytest.mark.asyncio

@pytest.fixture
def db_manager(event_loop):
    """Fixture pour initialiser le gestionnaire de base de données pour les tests."""
    logger.info("Initialisation de la base de données en mémoire pour les tests...")

    manager = DatabaseManager(database_url="sqlite+aiosqlite:///:memory:")

    async def setup():
        await manager.create_table()
        return manager

    return event_loop.run_until_complete(setup())




@pytest.fixture
def test_uid():
    """Fixture pour générer un UID de test unique."""
    return str(uuid.uuid4())

@pytest.fixture
def sample_schedule_data(test_uid):
    """Fixture pour créer des données d'exemple de planification."""
    now = datetime.now()
    return {
        "uid": test_uid,
        "name": "Test Schedule",
        "active": True,
        "cron_start": "0 8 * * 1-5",
        "cron_stop": "0 18 * * 1-5",
        "last_update": now.isoformat() + "Z"
    }

@pytest.fixture
def stored_schedule(db_manager, event_loop, test_uid):
    """Fixture pour stocker une planification de test dans la base de données."""

    async def store():
        await db_manager.store_uid(test_uid, "Test Workload")
        return await db_manager.get_schedule(test_uid)

    return event_loop.run_until_complete(store())


async def test_store_uid(db_manager, test_uid):
    logger.info(f"Test: Stockage de l'UID {test_uid}")
    await db_manager.store_uid(test_uid, "Test Workload")
    schedule = await db_manager.get_schedule(test_uid)
    assert schedule is not None
    assert schedule.name == "Test Workload"
    logger.success(f"UID {test_uid} stocké avec succès")

async def test_store_schedule_status(db_manager, sample_schedule_data):
    logger.info("Test: Stockage d'un statut de planification")
    schedule_obj = await db_manager.store_schedule_status(sample_schedule_data)
    assert schedule_obj is not None
    assert schedule_obj.uid == sample_schedule_data["uid"]
    assert schedule_obj.name == "Test Schedule"
    logger.success("Statut stocké avec succès")

async def test_get_all_schedules(db_manager, stored_schedule):
    logger.info("Test: Récupération de toutes les planifications")
    schedules = await db_manager.get_all_schedules()
    assert schedules is not None
    assert len(schedules) > 0
    for schedule in schedules:
        logger.info(f"ID: {schedule.id}, Nom: {schedule.name}, UID: {schedule.uid}")

async def test_update_schedule(db_manager, stored_schedule):
    logger.info("Test: Mise à jour d'une planification")
    stored_schedule.name = "Test Schedule Updated"
    stored_schedule.cron_start = "0 9 * * 1-5"
    success = await db_manager.update_schedule(stored_schedule.id, stored_schedule)
    assert success
    updated_schedule = await db_manager.get_schedule(stored_schedule.uid)
    assert updated_schedule.name == "Test Schedule Updated"
    assert updated_schedule.cron_start == "0 9 * * 1-5"
    logger.success("Planification mise à jour avec succès")

async def test_delete_schedule(db_manager, stored_schedule):
    logger.info(f"Test: Suppression de la planification avec ID {stored_schedule.id}")
    success = await db_manager.delete_schedule(stored_schedule.id)
    assert success
    deleted_schedule = await db_manager.get_schedule(stored_schedule.uid)
    assert deleted_schedule is None
    logger.success("Planification supprimée avec succès")

@pytest.fixture
def mock_db_manager():
    with patch('core.dbManager.DatabaseManager') as mock_manager:
        instance = mock_manager.return_value
        instance.create_table = AsyncMock()
        instance.store_uid = AsyncMock()
        instance.get_schedule = AsyncMock()
        instance.store_schedule_status = AsyncMock()
        instance.get_all_schedules = AsyncMock()
        instance.update_schedule = AsyncMock()
        instance.delete_schedule = AsyncMock()
        instance.close = AsyncMock()
        yield instance

async def test_store_uid_mock(mock_db_manager, test_uid):
    mock_schedule = WorkloadSchedule(id=1, uid=test_uid, name="Test Workload")
    mock_db_manager.get_schedule.return_value = mock_schedule
    await mock_db_manager.store_uid(test_uid, "Test Workload")
    schedule = await mock_db_manager.get_schedule(test_uid)
    assert schedule is not None
    assert schedule.name == "Test Workload"
    mock_db_manager.store_uid.assert_called_once_with(test_uid, "Test Workload")
    mock_db_manager.get_schedule.assert_called_once_with(test_uid)
