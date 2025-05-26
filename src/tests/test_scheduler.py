import pytest
from unittest.mock import MagicMock, patch, AsyncMock, call
import sys
import os
import asyncio
import datetime
import pytz
from types import SimpleNamespace

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scheduler_engine import SchedulerEngine
from core.models import ScheduleStatus


@pytest.fixture
def scheduler():
    with patch('scheduler_engine.RetryableAsyncClient') as mock_client:
        engine = SchedulerEngine(check_interval=1)
        engine.client = mock_client
        yield engine


@pytest.fixture
def mock_schedule():
    schedule = SimpleNamespace(
        id=1,
        name="test-workload",
        uid="test-uid-123",
        active=True,
        status=ScheduleStatus.NOT_SCHEDULED,
        cron_start="*/1 * * * *",
        cron_stop="*/2 * * * *",
        last_update=datetime.datetime.now()
    )
    return schedule


@pytest.fixture
def mock_scheduled_workload():
    schedule = SimpleNamespace(
        id=2,
        name="scheduled-workload",
        uid="scheduled-uid-456",
        active=True,
        status=ScheduleStatus.SCHEDULED,
        cron_start="*/1 * * * *",
        cron_stop="*/2 * * * *",
        last_update=datetime.datetime.now()
    )
    return schedule


@pytest.fixture
def mock_response():
    response = MagicMock()
    response.json.return_value = {"status": "success"}
    return response


@pytest.mark.asyncio
async def test_start(scheduler):
    with patch('asyncio.create_task') as mock_create_task:
        await scheduler.start()
        
        assert scheduler.running is True
        mock_create_task.assert_called_once()
        
        with patch('scheduler_engine.logger') as mock_logger:
            await scheduler.start()
            mock_logger.warning.assert_called_once()


@pytest.mark.asyncio
async def test_stop(scheduler):
    async def dummy_coroutine():
        await asyncio.sleep(0)

    task = asyncio.create_task(dummy_coroutine())
    task.cancel = AsyncMock()

    scheduler._task = task
    scheduler.running = True

    await scheduler.stop()

    assert scheduler.running is False
    task.cancel.assert_called_once()

    with patch('scheduler_engine.logger') as mock_logger:
        await scheduler.stop()
        mock_logger.warning.assert_called_once()


@pytest.mark.asyncio
async def test_run_normal_execution(scheduler):
    scheduler.running = True
    
    scheduler._check_schedules = AsyncMock()
    
    with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
        def side_effect(*args, **kwargs):
            scheduler.running = False
            future = asyncio.Future()
            future.set_result(None)
            return future
            
        mock_sleep.side_effect = side_effect
        
        await scheduler._run()
        
        scheduler._check_schedules.assert_called_once()


@pytest.mark.asyncio
async def test_run_with_exception(scheduler):
    scheduler.running = True
    
    scheduler._check_schedules = AsyncMock(side_effect=Exception("Test exception"))
    
    with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
        async def sleep_side_effect(*args, **kwargs):
            scheduler.running = False
            return None
            
        mock_sleep.side_effect = sleep_side_effect
        
        with patch('scheduler_engine.logger') as mock_logger:
            await scheduler._run()
            
            mock_logger.error.assert_called()
            mock_sleep.assert_called_once_with(1)


@pytest.mark.asyncio
async def test_run_cancelled(scheduler):
    scheduler.running = True
    
    scheduler._check_schedules = AsyncMock()
    
    with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep, \
         patch('scheduler_engine.logger') as mock_logger:
        mock_sleep.side_effect = asyncio.CancelledError()
        
        with pytest.raises(asyncio.CancelledError):
            await scheduler._run()
        
        mock_logger.info.assert_called_with("Tâche de scheduling annulée")


@pytest.mark.asyncio
async def test_check_schedules_normal(scheduler):
    schedule1 = SimpleNamespace(id=1, name="schedule1", uid="uid1", active=True)
    schedule2 = SimpleNamespace(id=2, name="schedule2", uid="uid2", active=True)
    
    mock_response = MagicMock()
    mock_response.json.return_value = [
        {"id": 1, "name": "schedule1", "uid": "uid1", "active": True},
        {"id": 2, "name": "schedule2", "uid": "uid2", "active": True}
    ]
    scheduler.client.get = AsyncMock(return_value=mock_response)
    
    scheduler._process_schedule = AsyncMock()
    
    await scheduler._check_schedules()
    
    scheduler.client.get.assert_called_once()
    
    assert scheduler._process_schedule.call_count == 2


@pytest.mark.asyncio
async def test_check_schedules_empty(scheduler):
    mock_response = MagicMock()
    mock_response.json.return_value = []
    scheduler.client.get = AsyncMock(return_value=mock_response)
    
    with patch('scheduler_engine.logger') as mock_logger:
        await scheduler._check_schedules()
        
        scheduler.client.get.assert_called_once()
        
        mock_logger.info.assert_any_call("Aucune programmation trouvée dans la base de données")


@pytest.mark.asyncio
async def test_check_schedules_exception(scheduler):
    scheduler.client.get = AsyncMock(side_effect=Exception("API Error"))
    
    with patch('scheduler_engine.logger') as mock_logger:
        await scheduler._check_schedules()
        
        mock_logger.error.assert_called()
        mock_logger.exception.assert_called()


@pytest.mark.asyncio
async def test_process_schedule_start(scheduler, mock_schedule):
    scheduler._should_execute = MagicMock(side_effect=[True, False])
    
    scheduler._start_workload = AsyncMock()
    
    now = datetime.datetime.now(pytz.timezone('Europe/Paris'))
    await scheduler._process_schedule(mock_schedule, now)
    
    scheduler._start_workload.assert_called_once_with(mock_schedule)
    
    scheduler._should_execute.assert_has_calls([
        call(mock_schedule.cron_start, now),
        call(mock_schedule.cron_stop, now)
    ])


@pytest.mark.asyncio
async def test_process_schedule_stop(scheduler, mock_scheduled_workload):
    scheduler._should_execute = MagicMock(side_effect=[False, True])
    
    scheduler._stop_workload = AsyncMock()
    
    now = datetime.datetime.now(pytz.timezone('Europe/Paris'))
    await scheduler._process_schedule(mock_scheduled_workload, now)
    
    scheduler._stop_workload.assert_called_once_with(mock_scheduled_workload)


@pytest.mark.asyncio
async def test_process_schedule_inactive(scheduler):
    schedule = SimpleNamespace(
        id=3,
        name="inactive-workload",
        uid="inactive-uid-789",
        active=False,
        status=ScheduleStatus.NOT_SCHEDULED,
        cron_start="*/1 * * * *",
        cron_stop="*/2 * * * *"
    )
    
    scheduler._should_execute = MagicMock(side_effect=[True, False])
    
    scheduler._start_workload = AsyncMock()
    
    now = datetime.datetime.now(pytz.timezone('Europe/Paris'))
    await scheduler._process_schedule(schedule, now)
    
    scheduler._start_workload.assert_called_once_with(schedule)


@pytest.mark.asyncio
async def test_process_schedule_stop_inactive(scheduler):
    schedule = SimpleNamespace(
        id=4,
        name="inactive-scheduled",
        uid="inactive-sched-012",
        active=False,
        status=ScheduleStatus.SCHEDULED,
        cron_start="*/1 * * * *",
        cron_stop="*/2 * * * *"
    )
    
    scheduler._should_execute = MagicMock(side_effect=[False, True])
    
    scheduler._stop_workload = AsyncMock()
    
    now = datetime.datetime.now(pytz.timezone('Europe/Paris'))
    await scheduler._process_schedule(schedule, now)
    
    scheduler._stop_workload.assert_not_called()


@pytest.mark.asyncio
async def test_process_schedule_exception(scheduler, mock_schedule):
    scheduler._should_execute = MagicMock(side_effect=Exception("Test exception"))
    
    with patch('scheduler_engine.logger') as mock_logger:
        now = datetime.datetime.now(pytz.timezone('Europe/Paris'))
        await scheduler._process_schedule(mock_schedule, now)
        
        mock_logger.error.assert_called()
        mock_logger.exception.assert_called()


def test_should_execute_no_cron(scheduler):
    now = datetime.datetime.now(pytz.timezone('Europe/Paris'))
    result = scheduler._should_execute(None, now)
    
    assert result is False


def test_should_execute_valid_cron_match(scheduler):
    now = datetime.datetime(2025, 5, 13, 12, 0, 0, tzinfo=pytz.timezone('Europe/Paris'))
    
    with patch('scheduler_engine.croniter') as mock_croniter:
        mock_cron_instance = MagicMock()
        mock_croniter.return_value = mock_cron_instance
        
        prev_time = now - datetime.timedelta(seconds=0.5)
        next_time = now + datetime.timedelta(seconds=0.5)
        
        mock_cron_instance.get_prev = MagicMock(return_value=prev_time)
        mock_cron_instance.get_next = MagicMock(return_value=next_time)
        
        result = scheduler._should_execute("*/1 * * * *", now)
        
        assert result is True, "La méthode devrait retourner True quand un cron est exécutable"
        

def test_should_execute_valid_cron_no_match(scheduler):
    now = datetime.datetime(2025, 5, 13, 12, 0, 0, tzinfo=pytz.timezone('Europe/Paris'))
    
    with patch('scheduler_engine.croniter') as mock_croniter:
        mock_cron_instance = MagicMock()
        mock_croniter.return_value = mock_cron_instance
        
        prev_time = now - datetime.timedelta(seconds=120)
        next_time = now + datetime.timedelta(seconds=120)
        
        mock_cron_instance.get_next.return_value = next_time
        mock_cron_instance.get_prev.return_value = prev_time
        
        result = scheduler._should_execute("*/2 * * * *", now)
        
        assert result is False


def test_should_execute_exception(scheduler):
    now = datetime.datetime.now(pytz.timezone('Europe/Paris'))
    
    with patch('scheduler_engine.croniter') as mock_croniter, \
         patch('scheduler_engine.logger') as mock_logger:
        mock_croniter.side_effect = Exception("Invalid cron expression")
        
        result = scheduler._should_execute("invalid-cron", now)
        
        assert result is False
        mock_logger.error.assert_called()


@pytest.mark.asyncio
async def test_start_workload_success(scheduler, mock_schedule, mock_response):
    scheduler.client.get = AsyncMock(return_value=mock_response)
    scheduler.client.put = AsyncMock(return_value=mock_response)
    
    with patch('scheduler_engine.logger') as mock_logger:
        await scheduler._start_workload(mock_schedule)
        
        scheduler.client.get.assert_called_once()
        scheduler.client.put.assert_called_once()
        
        mock_logger.success.assert_called()


@pytest.mark.asyncio
async def test_start_workload_api_error(scheduler, mock_schedule, mock_response):
    mock_response.json.return_value = {"status": "error", "message": "API Error"}
    scheduler.client.get = AsyncMock(return_value=mock_response)
    
    with patch('scheduler_engine.logger') as mock_logger:
        await scheduler._start_workload(mock_schedule)
        
        scheduler.client.get.assert_called_once()
        
        assert not scheduler.client.put.called
        
        mock_logger.error.assert_called()


@pytest.mark.asyncio
async def test_start_workload_exception(scheduler, mock_schedule):
    scheduler.client.get = AsyncMock(side_effect=Exception("Network error"))
    
    with patch('scheduler_engine.logger') as mock_logger:
        await scheduler._start_workload(mock_schedule)
        
        mock_logger.error.assert_called()
        mock_logger.exception.assert_called()


@pytest.mark.asyncio
async def test_stop_workload_success(scheduler, mock_scheduled_workload, mock_response):
    scheduler.client.get = AsyncMock(return_value=mock_response)
    scheduler.client.put = AsyncMock(return_value=mock_response)
    
    with patch('scheduler_engine.logger') as mock_logger:
        await scheduler._stop_workload(mock_scheduled_workload)
        
        scheduler.client.get.assert_called_once()
        scheduler.client.put.assert_called_once()
        
        mock_logger.success.assert_called()


@pytest.mark.asyncio
async def test_stop_workload_api_error(scheduler, mock_scheduled_workload, mock_response):
    mock_response.json.return_value = {"status": "error", "message": "API Error"}
    scheduler.client.get = AsyncMock(return_value=mock_response)
    
    with patch('scheduler_engine.logger') as mock_logger:
        await scheduler._stop_workload(mock_scheduled_workload)
        
        scheduler.client.get.assert_called_once()
        
        assert not scheduler.client.put.called
        
        mock_logger.error.assert_called()


@pytest.mark.asyncio
async def test_stop_workload_exception(scheduler, mock_scheduled_workload):
    scheduler.client.get = AsyncMock(side_effect=Exception("Network error"))
    
    with patch('scheduler_engine.logger') as mock_logger:
        await scheduler._stop_workload(mock_scheduled_workload)
        
        mock_logger.error.assert_called()
        mock_logger.exception.assert_called()


@pytest.mark.asyncio
async def test_init():
    scheduler = SchedulerEngine()
    assert scheduler.check_interval == 60
    assert scheduler.running is False
    assert scheduler._task is None
    assert scheduler.timezone.zone == 'Europe/Paris'
    
    scheduler = SchedulerEngine(check_interval=30)
    assert scheduler.check_interval == 30
    
    with patch.dict('os.environ', {'TIMEZONE': 'America/New_York'}):
        scheduler = SchedulerEngine()
        assert scheduler.timezone.zone == 'America/New_York'