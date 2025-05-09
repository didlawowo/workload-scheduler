import pytest
from unittest.mock import patch, MagicMock, mock_open
import json
import os
import sys
import requests
from datetime import datetime, timedelta
from jwt import encode as jwt_encode

# Import the module to test
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.argocd import ArgoTokenManager, handle_argocd_auto_sync, enable_auto_sync, patch_argocd_application

class TestArgoTokenManager:
    
    @pytest.fixture
    def token_manager(self):
        """Fixture pour créer une instance d'ArgoTokenManager avec des mocks"""
        with patch.dict(os.environ, {
            "ARGOCD_API_URL": "http://argocd-test:8080/api/v1",
            "ARGOCD_USERNAME": "test-user",
            "ARGOCD_PASSWORD": "test-password",
            "JWT_SECRET_KEY": "test-secret-key"
        }):
            manager = ArgoTokenManager()
            yield manager
    
    @pytest.fixture
    def mock_response(self):
        """Fixture pour créer une réponse mock pour les requêtes"""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        
        # Créer un token JWT valide pour la réponse mock
        payload = {
            "iat": datetime.now(),
            "exp": (datetime.now() + timedelta(hours=1)).timestamp(),
            "sub": "test-user"
        }
        token = jwt_encode(payload, "test-secret-key", algorithm="HS256")
        if isinstance(token, bytes):
            token = token.decode('utf-8')
            
        mock_resp.json.return_value = {"token": token}
        return mock_resp
    
    @pytest.fixture
    def mock_response_expired(self):
        """Fixture pour créer une réponse mock avec un token expiré"""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        
        # Créer un token JWT expiré
        payload = {
            "iat": (datetime.now() - timedelta(hours=2)),
            "exp": (datetime.now() - timedelta(hours=1)).timestamp(),
            "sub": "test-user"
        }
        token = jwt_encode(payload, "test-secret-key", algorithm="HS256")
        if isinstance(token, bytes):
            token = token.decode('utf-8')
            
        mock_resp.json.return_value = {"token": token}
        return mock_resp
    
    def test_singleton_pattern(self):
        """Test pour vérifier que ArgoTokenManager est un singleton"""
        manager1 = ArgoTokenManager()
        manager2 = ArgoTokenManager()
        
        assert manager1 is manager2
        assert id(manager1) == id(manager2)
    
    def test_authenticate_success(self, token_manager, mock_response):
        """Test d'authentification réussie"""
        with patch('requests.post', return_value=mock_response):
            token = token_manager._authenticate()
            
            assert token is not None
            assert token == mock_response.json()["token"]
            requests.post.assert_called_once_with(
                f"{token_manager.ARGOCD_API_URL}/session",
                headers=token_manager.headers,
                data=json.dumps({"username": token_manager.USERNAME, "password": token_manager.PASSWORD}),
                timeout=5
            )
    
    def test_authenticate_failure(self, token_manager):
        """Test d'échec d'authentification"""
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.text = "Unauthorized"
        
        with patch('requests.post', return_value=mock_resp):
            token = token_manager._authenticate()
            
            assert token is None
            requests.post.assert_called_once()
    
    def test_authenticate_exception(self, token_manager):
        """Test d'exception pendant l'authentification"""
        with patch('requests.post', side_effect=Exception("Connection error")):
            token = token_manager._authenticate()
            
            assert token is None
            requests.post.assert_called_once()
    
    def test_verify_signature_success(self, token_manager, mock_response):
        """Test de vérification de signature réussie"""
        token = mock_response.json()["token"]
        secret_key = "test-secret-key"
        
        result = token_manager._verify_signature(token, secret_key)
        
        assert result is True
    
    def test_verify_signature_failure(self, token_manager, mock_response):
        """Test d'échec de vérification de signature"""
        token = mock_response.json()["token"]
        secret_key = "wrong-secret-key"
        
        result = token_manager._verify_signature(token, secret_key)
        
        assert result is False
    
    def test_verify_token_valid(self, token_manager, mock_response):
        """Test de vérification d'un token valide"""
        token = mock_response.json()["token"]
        
        with patch.object(token_manager, '_verify_signature', return_value=True):
            result = token_manager._verify_token(token)
            
            assert result == token
            token_manager._verify_signature.assert_called_once()
    
    def test_verify_token_expired(self, token_manager, mock_response_expired):
        """Test de vérification d'un token expiré"""
        token = mock_response_expired.json()["token"]
        
        with patch.object(token_manager, '_authenticate', return_value="new-token"):
            result = token_manager._verify_token(token)
            
            assert result == "new-token"
            token_manager._authenticate.assert_called_once()
    
    def test_get_token_first_call(self, token_manager):
        """Test de récupération de token pour le premier appel"""
        with patch.object(token_manager, '_authenticate', return_value="test-token"):
            token = token_manager.get_token()
            
            assert token == "test-token"
            token_manager._authenticate.assert_called_once()
    
    def test_get_token_cached(self, token_manager):
        """Test de récupération de token en cache"""
        token_manager.token = "cached-token"
        
        with patch.object(token_manager, '_verify_token', return_value="verified-token"):
            token = token_manager.get_token()
            
            assert token == "verified-token"
            token_manager._verify_token.assert_called_once_with("cached-token")
    
    def test_get_token_force_refresh(self, token_manager):
        """Test de rafraîchissement forcé du token"""
        token_manager.token = "old-token"
        
        with patch.object(token_manager, '_authenticate', return_value="new-token"):
            token = token_manager.get_token(force_refresh=True)
            
            assert token == "new-token"
            token_manager._authenticate.assert_called_once()


class TestArgocdFunctions:
    
    @pytest.fixture
    def mock_token_manager(self):
        """Fixture pour mocker ArgoTokenManager"""
        with patch('utils.argocd.ArgoTokenManager') as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.ARGOCD_API_URL = "http://argocd-test:8080/api/v1"
            mock_manager.get_token.return_value = "test-token"
            
            mock_manager_class.return_value = mock_manager
            yield mock_manager
    
    @pytest.fixture
    def mock_resource(self):
        """Fixture pour créer un resource mock"""
        resource = MagicMock()
        resource.metadata.labels = {"argocd.argoproj.io/instance": "test-app"}
        return resource
    
    @pytest.fixture
    def mock_app_config(self):
        """Fixture pour créer une configuration d'application mock"""
        return {
            "spec": {
                "syncPolicy": {
                    "automated": {
                        "prune": True,
                        "selfHeal": True
                    }
                }
            }
        }
    
    @pytest.fixture
    def mock_app_config_no_auto_sync(self):
        """Fixture pour créer une configuration sans auto-sync"""
        return {
            "spec": {
                "syncPolicy": {}
            }
        }
    
    def test_handle_argocd_auto_sync(self, mock_token_manager, mock_resource):
        """Test de gestion de l'auto-sync ArgoCD"""
        with patch('utils.argocd.enable_auto_sync') as mock_enable_auto_sync:
            handle_argocd_auto_sync(mock_resource)
            
            mock_enable_auto_sync.assert_called_once_with("test-app")
    
    def test_handle_argocd_auto_sync_no_label(self, mock_token_manager):
        """Test de gestion de l'auto-sync sans étiquette ArgoCD"""
        resource = MagicMock()
        resource.metadata.labels = {}
        
        with patch('utils.argocd.enable_auto_sync') as mock_enable_auto_sync:
            handle_argocd_auto_sync(resource)
            
            mock_enable_auto_sync.assert_not_called()
    
    def test_enable_auto_sync_success(self, mock_token_manager, mock_app_config):
        """Test d'activation réussie de l'auto-sync"""
        mock_get_resp = MagicMock()
        mock_get_resp.status_code = 200
        mock_get_resp.json.return_value = mock_app_config
        
        with patch('requests.get', return_value=mock_get_resp):
            with patch('utils.argocd.patch_argocd_application') as mock_patch:
                enable_auto_sync("test-app")
                
                mock_patch.assert_called_once_with(
                    app_name="test-app",
                    enable_auto_sync=True
                )
                requests.get.assert_called_once_with(
                    f"{mock_token_manager.ARGOCD_API_URL}/applications/test-app",
                    headers={"Authorization": "Bearer test-token", "Content-Type": "application/json"},
                    timeout=3
                )
    
    def test_enable_auto_sync_app_not_found(self, mock_token_manager):
        """Test d'activation de l'auto-sync pour une application non trouvée"""
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        
        with patch('requests.get', return_value=mock_resp):
            with patch('utils.argocd.patch_argocd_application') as mock_patch:
                enable_auto_sync("non-existent-app")
                
                mock_patch.assert_not_called()
    
    def test_enable_auto_sync_exception(self, mock_token_manager):
        """Test d'exception lors de l'activation de l'auto-sync"""
        with patch('requests.get', side_effect=Exception("API error")):
            with patch('utils.argocd.patch_argocd_application') as mock_patch:
                enable_auto_sync("test-app")
                
                mock_patch.assert_not_called()
    
    def test_patch_argocd_application_enable_auto_sync(self, mock_token_manager, mock_app_config_no_auto_sync):
        """Test de modification d'application pour activer l'auto-sync"""
        mock_get_resp = MagicMock()
        mock_get_resp.status_code = 200
        mock_get_resp.json.return_value = mock_app_config_no_auto_sync
        
        mock_put_resp = MagicMock()
        mock_put_resp.status_code = 200
        
        with patch('requests.get', return_value=mock_get_resp):
            with patch('requests.put', return_value=mock_put_resp):
                patch_argocd_application("test-app", enable_auto_sync=False)
                
                # Vérifier que l'auto-sync a été activé dans la requête PUT
                called_args = requests.put.call_args
                called_url, called_kwargs = called_args[0][0], called_args[1]
                called_data = json.loads(called_kwargs['data'])
                
                assert called_url == f"{mock_token_manager.ARGOCD_API_URL}/applications/test-app?validate=false"
                assert "automated" in called_data["spec"]["syncPolicy"]
                assert called_data["spec"]["syncPolicy"]["automated"]["prune"] is True
                assert called_data["spec"]["syncPolicy"]["automated"]["selfHeal"] is True
    
    def test_patch_argocd_application_disable_auto_sync(self, mock_token_manager, mock_app_config):
        """Test de modification d'application pour désactiver l'auto-sync"""
        mock_get_resp = MagicMock()
        mock_get_resp.status_code = 200
        mock_get_resp.json.return_value = mock_app_config
        
        mock_put_resp = MagicMock()
        mock_put_resp.status_code = 200
        
        with patch('requests.get', return_value=mock_get_resp):
            with patch('requests.put', return_value=mock_put_resp):
                patch_argocd_application("test-app", enable_auto_sync=True)
                
                # Vérifier que l'auto-sync a été désactivé dans la requête PUT
                called_args = requests.put.call_args
                called_url, called_kwargs = called_args[0][0], called_args[1]
                called_data = json.loads(called_kwargs['data'])
                
                assert called_url == f"{mock_token_manager.ARGOCD_API_URL}/applications/test-app?validate=false"
                assert called_data["spec"]["syncPolicy"]["automated"] is None
    
    def test_patch_argocd_application_failure(self, mock_token_manager, mock_app_config):
        """Test d'échec de modification d'application"""
        mock_get_resp = MagicMock()
        mock_get_resp.status_code = 200
        mock_get_resp.json.return_value = mock_app_config
        
        mock_put_resp = MagicMock()
        mock_put_resp.status_code = 400
        mock_put_resp.text = "Bad Request"
        
        with patch('requests.get', return_value=mock_get_resp):
            with patch('requests.put', return_value=mock_put_resp):
                # Aucune assertion directe, vérifie juste que la fonction ne lève pas d'exception
                patch_argocd_application("test-app", enable_auto_sync=True)