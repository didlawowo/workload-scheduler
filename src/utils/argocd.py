from datetime import datetime
import requests
import json
from loguru import logger
import os
import sys
from icecream import ic
from jwt import encode as jwt_encode, decode as jwt_decode
import urllib3

# Disable SSL warnings for unverified HTTPS requests
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class ArgoTokenManager:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ArgoTokenManager, cls).__new__(cls)
            cls._instance.token = None
            cls._instance.ARGOCD_API_URL = os.getenv("ARGOCD_API_URL", "http://localhost:8080/api/v1")
            cls._instance.USERNAME = os.getenv("ARGOCD_USERNAME", "admin")
            cls._instance.PASSWORD = os.getenv("ARGOCD_PASSWORD", "admin")
            cls._instance.headers = {"Content-Type": "application/json"}
        return cls._instance
    
    def get_token(self, force_refresh=False):
        if not self.token or force_refresh:
            self.token = self._authenticate()
            if not self.token:
                logger.error("Failed to authenticate with ArgoCD. Exiting program.")
                sys.exit(1)  # Stop program if authentication fails
        else:
            self.token = self._verify_token(self.token)
            if not self.token:
                logger.error("Token verification failed. Could not connect to ArgoCD. Exiting program.")
                sys.exit(1)  # Stop program if token verification fails
        return self.token
    
    def _authenticate(self):
        """
        Authenticates with the Argo CD API using username and password to obtain a session token.
        """
        logger.info("Authenticating with Argo CD...")
        
        auth_payload = {"username": self.USERNAME, "password": self.PASSWORD}
        
        try:
            response = requests.post(
                f"{self.ARGOCD_API_URL}/session",
                headers=self.headers,
                data=json.dumps(auth_payload),
                timeout=5,
            )

            if response.status_code == 200:
                session_token = response.json()["token"]
                logger.success("Successfully authenticated with Argo CD.")
                return session_token
            logger.error(
                f"Failed to authenticate with Argo CD. Status code: {response.status_code}, Response: {response.text}"
            )
            return None
        except Exception as e:
            logger.error(f"Exception during authentication with Argo CD: {str(e)}")
            return None

    def _verify_signature(self, token, secret_key):
        """
        Vérifie la signature du token sans modifier le token original.
        Lève une exception si la signature n'est pas valide.
        """
        try:
            payload = jwt_decode(token, options={'verify_signature': False})
            
            new_token = jwt_encode(payload, secret_key, algorithm="HS256")
            
            if isinstance(new_token, bytes):
                new_token = new_token.decode('utf-8')
            if isinstance(token, bytes):
                token = token.decode('utf-8')
                
            token_parts = token.split('.')
            new_token_parts = new_token.split('.')
            
            if len(token_parts) >= 3 and len(new_token_parts) >= 3:
                if token_parts[2] == new_token_parts[2]:
                    logger.debug("Token signature verified successfully")
                    return True
                else:
                    logger.warning("Token signature verification failed: signatures don't match")
                    return False
            else:
                logger.warning("Invalid token format for signature verification")
                return False
                
        except Exception as e:
            logger.error(f"Token signature verification failed: {e}")
            return False

    def _verify_token(self, token):
        """
        Verifies if the token is valid. If not, obtains a new one.
        Returns the valid token.
        """
        try:
            decode_token = jwt_decode(token, options={'verify_signature': False})
            date_token = datetime.fromtimestamp(decode_token.get("exp"))
            logger.debug(f"Token expiration: {date_token}")

            current_time = datetime.now()
            is_expired = date_token < current_time
            logger.debug(f"Token expired: {is_expired}")

            if is_expired:
                logger.info("Token expired, getting new token")
                return self._authenticate()

            return token
        except Exception as e:
            logger.error(f"Error verifying token: {e}")
            return self._authenticate()
        
def handle_argocd_auto_sync(resource):
    token_manager = ArgoTokenManager()
    if (token_manager.ARGOCD_API_URL and resource.metadata.labels and "argocd.argoproj.io/instance" in resource.metadata.labels):
        
        instance_name = resource.metadata.labels["argocd.argoproj.io/instance"]
        enable_auto_sync(instance_name)

def enable_auto_sync(application_name):
    """
    Désactive temporairement l'auto-sync ArgoCD pour permettre le scale-down manuel.
    Sauvegarde l'état initial pour pouvoir le restaurer plus tard.
    """
    try:
        logger.debug(f"Application name: {application_name}")
        token_manager = ArgoTokenManager()
        token = token_manager.get_token()

        logger.info(f"Checking auto-sync status for application '{application_name}'")

        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        res = requests.get(
            f"{token_manager.ARGOCD_API_URL}/applications/{application_name}",
            headers=headers,
            timeout=3,
            verify=False
        )

        if res.status_code != 200:
            logger.error(f"ArgoCD application '{application_name}' not found or API error: {res.status_code}. Exiting program")
            sys.exit(1)  # Stop program if application not found

        app_config = res.json()

        auto_sync_enabled = False
        if "spec" in app_config:
            sync_policy = app_config["spec"].get("syncPolicy", {})
            if "automated" in sync_policy:
                auto_sync_enabled = True

        if auto_sync_enabled:
            logger.info(f"Auto-sync is currently ENABLED for '{application_name}'. Disabling it to allow manual scaling.")
            patch_argocd_application(
                app_name=application_name,
                enable_auto_sync=False,
            )
            logger.success(f"Auto-sync disabled for application '{application_name}'. Proceeding with scaling.")
        else:
            logger.info(f"Auto-sync is already DISABLED for '{application_name}'. No action needed.")

    except Exception as e:
        logger.error(f"Error handling auto-sync for application '{application_name}': {e}. Exiting program.")
        sys.exit(1)  # Stop program on exception

def patch_argocd_application(app_name, enable_auto_sync):
    """
    Send a PATCH request to modify an Argo CD application.
    """
    token_manager = ArgoTokenManager()
    token = token_manager.get_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    
    try:
        res = requests.get(
            f"{token_manager.ARGOCD_API_URL}/applications/{app_name}", headers=headers, timeout=3
        )
        
        if res.status_code != 200:
            logger.error(f"Failed to fetch application '{app_name}'. Status code: {res.status_code}. Exiting program.")
            sys.exit(1)  # Stop program if application not found
            
        app_config = res.json()
        logger.debug(app_config["spec"])

        if enable_auto_sync:
            logger.info("enabling auto sync")
            if "syncPolicy" not in app_config["spec"]:
                app_config["spec"]["syncPolicy"] = {}
            app_config["spec"]["syncPolicy"]["automated"] = {
                "prune": True,
                "selfHeal": True,
            }
            logger.debug(app_config["spec"])
        else:
            logger.info("disabling auto sync")
            if "syncPolicy" in app_config["spec"] and "automated" in app_config["spec"]["syncPolicy"]:
                del app_config["spec"]["syncPolicy"]["automated"]
            logger.debug(app_config["spec"])

        logger.info(f" app name {app_name}")

        response = requests.put(
            f"{token_manager.ARGOCD_API_URL}/applications/{app_name}?validate=false",
            headers=headers,
            data=json.dumps(app_config),
            timeout=10,
        )

        if response.status_code == 200:
            logger.success("Application patched successfully.")
        else:
            logger.error(
                f"Failed to patch the application. Status code: {response.status_code}, Response: {response.text}. Exiting program."
            )
            sys.exit(1)  # Stop program if patching fails
        
        # Verify the patch worked
        res = requests.get(
            f"{token_manager.ARGOCD_API_URL}/applications/{app_name}", headers=headers, timeout=5
        )
        
        if res.status_code != 200:
            logger.error(f"Failed to verify patch for application '{app_name}'. Status code: {res.status_code}. Exiting program.")
            sys.exit(1)  # Stop program if verification fails
            
        logger.info(f"policy {res.json()['spec']['syncPolicy']}")
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Network error while patching application: {e}. Exiting program.")
        sys.exit(1)  # Stop program on network error
    except Exception as e:
        logger.error(f"Unexpected error while patching application: {e}. Exiting program.")
        sys.exit(1)  # Stop program on unexpected error