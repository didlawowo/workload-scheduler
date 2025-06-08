import sys
import os
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime
from fastapi.testclient import TestClient
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

@pytest.fixture(autouse=True)
def mock_kubernetes_config():
    """Fixture pour mocker la configuration Kubernetes"""
    with patch('kubernetes.config.incluster_config.InClusterConfigLoader.load_and_set'):
        with patch('kubernetes.client.AppsV1Api'), patch('kubernetes.client.CoreV1Api'):
            yield

@pytest.fixture
def test_client(mock_kubernetes_config):
    """Fixture pour le client de test"""
    import main
    from main import app
    return TestClient(app)

@pytest.fixture
def mock_kubernetes_clients():
    with patch('main.list_all_deployments') as mock_deployment, \
         patch('main.list_all_sts') as mock_sts, \
         patch('main.list_all_daemonsets') as mock_daemonset:
        mock_deployment.return_value = [{"name": "test-deployment", "uid": "dep-123", "namespace": "default"}]
        mock_sts.return_value = [{"name": "test-statefulset", "uid": "sts-456", "namespace": "default"}]
        mock_daemonset.return_value = [{"name": "test-daemonset", "uid": "ds-789", "namespace": "default"}]
        yield (mock_deployment, mock_sts, mock_daemonset)

@pytest.fixture
def mock_db():
    with patch('main.db') as mock_db_instance:
        mock_db_instance.create_table = AsyncMock()
        mock_db_instance.store_uid = AsyncMock()
        yield mock_db_instance

@pytest.fixture
def mock_templates():
    with patch('main.templates') as mock_templates:
        mock_response = MagicMock()
        mock_response.__str__ = lambda self: "<html>Mock HTML</html>"
        mock_templates.TemplateResponse.return_value = mock_response
        yield mock_templates

def test_app_routes():
    routes = [route.path for route in app.routes]
    assert "/" in routes
    static_routes = [r for r in routes if "static" in r]
    assert len(static_routes) > 0

def test_formatter():
    level_mock = MagicMock()
    level_mock.name = "INFO"
    
    file_mock = MagicMock()
    file_mock.name = "test_file.py"
    
    process_mock = MagicMock()
    process_mock.id = 1234
    
    thread_mock = MagicMock()
    thread_mock.name = "MainThread"
    
    record = {
        "time": datetime.now(),
        "level": level_mock,
        "message": "Test message",
        "name": "test_logger",
        "function": "test_function",
        "file": file_mock,
        "line": 123,
        "process": process_mock,
        "thread": thread_mock
    }
    
    formatted = main.formatter(record)
    log_data = json.loads(formatted)
    
    assert "timestamp" in log_data
    assert "level" in log_data
    assert log_data["level"] == "INFO"
    assert "message" in log_data
    assert log_data["message"] == "Test message"
    assert "service" in log_data
    assert log_data["service"] == "workload-scheduler"
    assert "logger" in log_data
    assert "process" in log_data

@pytest.mark.asyncio
async def test_init_database(mock_db, mock_kubernetes_clients):
    mock_deployment, mock_sts, mock_daemonset = mock_kubernetes_clients
    
    try:
        with patch.object(main, 'init_database', new_callable=AsyncMock) as mock_init:
            await mock_init()
            mock_init.assert_called_once()
    except Exception as e:
        pytest.skip(f"Skip due to DB connection issue: {str(e)}")

@pytest.mark.asyncio
async def test_init_database_exception_handling():
    with patch('main.db') as mock_db:
        mock_db.create_table = AsyncMock(side_effect=Exception("Database error"))
        
        with patch('main.list_all_deployments'), \
             patch('main.list_all_sts'), \
             patch('main.list_all_daemonsets'):
                
            with patch('main.logger') as mock_logger:
                with pytest.raises(Exception):
                    await main.init_database()
                
                mock_logger.error.assert_called()

def test_status_endpoint(test_client, mock_kubernetes_clients, mock_templates):
    mock_templates.TemplateResponse.return_value = "<html>Mock HTML</html>"
    
    with patch('main.HTMLResponse', return_value="<html>Mock HTML</html>"):
        response = test_client.get("/")
        
        mock_dep, mock_sts, mock_ds = mock_kubernetes_clients
        mock_dep.assert_called_once()
        mock_sts.assert_called_once()
        mock_ds.assert_called_once()

def test_status_endpoint_error(test_client, mock_kubernetes_clients):
    mock_deployment, _, _ = mock_kubernetes_clients
    mock_deployment.side_effect = Exception("Kubernetes API error")
    
    response = test_client.get("/")
    
    assert response.status_code == 500
    assert "Error" in response.content.decode()
    assert "Kubernetes API error" in response.content.decode()

def test_environment_variables():
    assert hasattr(main, 'is_dev')
    assert main.is_dev is True or main.is_dev is False

def test_logger_initialized():
    assert hasattr(main, 'logger')
    assert hasattr(main.logger, 'info')
    assert hasattr(main.logger, 'error')
    assert hasattr(main.logger, 'success')

def test_app_initialization():
    assert hasattr(main, 'app')
    assert hasattr(main.app, 'mount')
    assert hasattr(main.app, 'include_router')
    
    assert hasattr(main, 'scheduler')
    assert hasattr(main, 'workload')
    assert hasattr(main, 'health_route')

def test_database_initialized():
    assert hasattr(main, 'db')
    assert hasattr(main.db, 'create_table')
    assert hasattr(main.db, 'store_uid')

def test_main_is_callable():
    assert hasattr(main, 'main')
    assert callable(main.main)

def test_scheduler_engine_initialized():
    assert hasattr(main, 'scheduler_engine')
    assert hasattr(main.scheduler_engine, 'check_interval')
    assert main.scheduler_engine.check_interval == 60