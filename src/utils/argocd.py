from datetime import datetime
import requests
import json
from loguru import logger
import os
from icecream import ic
from jwt import decode as jwt_decode

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
        else:
            self.token = self._verify_token(self.token)
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


# @logger.catch
# def get_argocd_session_token():
#     """
#     Authenticates with the Argo CD API using username and password to obtain a session token.
#     """
#     logger.info("Authenticating with Argo CD...")
#     auth_payload = {"username": USERNAME, "password": PASSWORD}
#     response = requests.post(
#         f"{ARGOCD_API_URL}/session",
#         headers=headers,
#         data=json.dumps(auth_payload),
#         timeout=5,
#     )

#     if response.status_code == 200:
#         session_token = response.json()["token"]
#         # logger.debug(f"Session token: {session_token}")
#         logger.success("Successfully authenticated with Argo CD.")
#         return session_token

#     logger.error(
#         f"Failed to authenticate with Argo CD. Status code: {response.status_code}, Response: {response.text}"
#     )
#     return None

# def verify_argocd_session_token(token):
#     decode_token = jwt_decode(token, options={'verify_signature': False})
#     date_token = datetime.fromtimestamp(decode_token.get("exp"))
#     logger.debug(date_token)

#     current_time = datetime.now()
#     is_expired = date_token < current_time
#     logger.debug(is_expired)

#     if is_expired:
#         argo_session_token = get_argocd_session_token()
#         return argo_session_token
#     return token
    

def enable_auto_sync(application_name):
    logger.debug(f"Application name: {application_name}")
    token_manager = ArgoTokenManager()
    token = token_manager.get_token()
    
    logger.info(f"Enabling auto-sync for application '{application_name}'")
    
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    res = requests.get(
        f"{token_manager.ARGOCD_API_URL}/applications/{application_name}", headers=headers, timeout=3
    )
    app_config = res.json()
    ic(token)
    
    auto_sync = False
    if "spec" in app_config:
        sync_policy = app_config["spec"].get("syncPolicy", {})
        if "automated" in sync_policy:
            auto_sync = True
    
    patch_argocd_application(
        app_name=application_name,
        enable_auto_sync=auto_sync,
    )
    
    logger.success(
        f"Auto-sync enabled for application '{application_name}'. Proceeding with scaling down the Deployment."
    )

def patch_argocd_application(app_name, enable_auto_sync):
    """
    Send a PATCH request to modify an Argo CD application.
    """
    token_manager = ArgoTokenManager()
    token = token_manager.get_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    res = requests.get(
        f"{token_manager.ARGOCD_API_URL}/applications/{app_name}", headers=headers, timeout=3
    )
    app_config = res.json()
    logger.debug(app_config["spec"])
    
    if enable_auto_sync:
        logger.info("disabling auto sync")
        app_config["spec"]["syncPolicy"]["automated"] = None
        logger.debug(app_config["spec"])
    if not enable_auto_sync:
        logger.info("enabling auto sync")
        app_config["spec"]["syncPolicy"]["automated"] = {
            "prune": True,
            "selfHeal": True,
        }

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
            f"Failed to patch the application. Status code: {response.status_code}, Response: {response.text}"
        )
    
    res = requests.get(
        f"{token_manager.ARGOCD_API_URL}/applications/{app_name}", headers=headers, timeout=5
    )
    logger.info(f"policy {res.json()['spec']['syncPolicy']}")