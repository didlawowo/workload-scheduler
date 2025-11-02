import json
import os
import sys
from datetime import datetime
from typing import Dict, Optional

import requests
import urllib3
from jwt import decode as jwt_decode
from jwt import encode as jwt_encode
from loguru import logger

# Disable SSL warnings for unverified HTTPS requests
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class ArgoTokenManager:
    _instance = None
    token: Optional[str]
    ARGOCD_API_URL: str
    USERNAME: str
    PASSWORD: str
    headers: Dict[str, str]

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
                raise Exception("Failed to authenticate with ArgoCD")
        else:
            self.token = self._verify_token(self.token)
            if not self.token:
                logger.error("Token verification failed. Could not connect to ArgoCD. Exiting program.")
                raise Exception("Token verification failed. Could not connect to ArgoCD.")
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
        
def find_argocd_application_for_resource(resource_name: str, resource_namespace: str, resource_labels: dict) -> list[str]:
    """
    Find the ArgoCD Application(s) managing this resource.

    Returns a list of Application names. Can be empty, single, or multiple Applications.

    Logic:
    1. Check for argocd.argoproj.io/instance label (explicit ArgoCD label)
    2. Check for app.kubernetes.io/instance label and find matching Application
    3. Fallback: match by namespace for all Applications with selfHeal enabled
    """
    try:
        from kubernetes import client, config

        # Try to load kubernetes config
        try:
            config.load_incluster_config()
        except:
            config.load_kube_config()

        # Check for explicit ArgoCD label first
        if resource_labels and "argocd.argoproj.io/instance" in resource_labels:
            return [resource_labels["argocd.argoproj.io/instance"]]

        # Query ArgoCD Applications via Kubernetes API
        custom_api = client.CustomObjectsApi()
        try:
            applications = custom_api.list_namespaced_custom_object(
                group="argoproj.io",
                version="v1alpha1",
                namespace="kube-infra",
                plural="applications"
            )

            # Check for app.kubernetes.io/instance label
            if resource_labels and "app.kubernetes.io/instance" in resource_labels:
                instance_name = resource_labels["app.kubernetes.io/instance"]

                # Find Application that matches this resource by instance name
                # Priority: exact match > suffix match > substring match
                exact_match = None
                suffix_match = None

                for app in applications.get("items", []):
                    app_name = app["metadata"]["name"]
                    app_spec = app.get("spec", {})
                    app_dest_ns = app_spec.get("destination", {}).get("namespace", "")

                    # Only consider Applications in the same namespace
                    if app_dest_ns != resource_namespace:
                        continue

                    logger.info(f"Checking Application '{app_name}' against instance '{instance_name}' in namespace '{resource_namespace}'")

                    # Exact match has highest priority
                    if app_name == instance_name:
                        logger.info(f"✅ Exact match found: '{app_name}' == '{instance_name}'")
                        exact_match = app_name
                        break

                    # Suffix match (e.g. in-cluster-portal-checker matches portal-checker)
                    # IMPORTANT: Only match if there's a delimiter before the instance name
                    if app_name.endswith("-" + instance_name):
                        logger.info(f"📌 Suffix match found: '{app_name}'.endswith('-{instance_name}')")
                        suffix_match = app_name

                # Return the best match found
                if exact_match:
                    logger.info(f"Found ArgoCD Application '{exact_match}' managing resource '{resource_name}' (exact match)")
                    return [exact_match]
                if suffix_match:
                    logger.info(f"Found ArgoCD Application '{suffix_match}' managing resource '{resource_name}' (suffix match)")
                    return [suffix_match]

            # Fallback: search by namespace only and check if Application has automated selfHeal enabled
            # This handles cases where resources don't have standard labels
            matching_apps = []
            for app in applications.get("items", []):
                app_name = app["metadata"]["name"]
                app_spec = app.get("spec", {})
                app_dest_ns = app_spec.get("destination", {}).get("namespace", "")
                sync_policy = app_spec.get("syncPolicy", {})
                automated = sync_policy.get("automated", {})

                # Match if destination namespace matches AND selfHeal is enabled
                if app_dest_ns == resource_namespace and automated.get("selfHeal"):
                    matching_apps.append(app_name)

            if len(matching_apps) == 1:
                # Only one Application manages this namespace with selfHeal - safe to assume it's the one
                logger.info(f"Found ArgoCD Application '{matching_apps[0]}' managing namespace '{resource_namespace}' (matched by namespace only)")
                return matching_apps
            elif len(matching_apps) > 1:
                logger.warning(f"Multiple ArgoCD Applications found for namespace '{resource_namespace}': {matching_apps}. Will disable auto-sync for all of them.")
                return matching_apps

        except Exception as e:
            logger.warning(f"Failed to query ArgoCD Applications: {e}")
            return []

        return []
    except Exception as e:
        logger.error(f"Error finding ArgoCD Application: {e}")
        return []

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

        # Skip ArgoCD operations if not configured (dev mode)
        if not token_manager.ARGOCD_API_URL or token_manager.ARGOCD_API_URL == "http://localhost:8080/api/v1":
            logger.info(f"ArgoCD not configured (dev mode), skipping auto-sync check for '{application_name}'")
            return

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
            raise Exception(f"Application '{application_name}' not found in Argo CD. Status code: {res.status_code}")

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

    except Exception as ex:
        logger.error(f"Error handling auto-sync for application '{application_name}': {ex}. Exiting program.")
        raise Exception(f"Error handling auto-sync for application '{application_name}': {ex}")

def patch_argocd_application(app_name, enable_auto_sync):
    """
    Send a PATCH request to modify an Argo CD application.
    """
    token_manager = ArgoTokenManager()
    token = token_manager.get_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    
    try:
        res = requests.get(
            f"{token_manager.ARGOCD_API_URL}/applications/{app_name}",
            headers=headers,
            timeout=3,
            verify=False
        )
        
        if res.status_code != 200:
            logger.error(f"Failed to fetch application '{app_name}'. Status code: {res.status_code}. Exiting program.")
            raise Exception(f"Application '{application_name}' not found in Argo CD. Status code: {res.status_code}")
            
        app_config = res.json()
        logger.debug(app_config["spec"])

        if enable_auto_sync:
            logger.info("enabling auto sync")
            if "syncPolicy" not in app_config["spec"]:
                app_config["spec"]["syncPolicy"] = {}
            if "automated" not in app_config["spec"]["syncPolicy"]:
                app_config["spec"]["syncPolicy"]["automated"] = {}
            app_config["spec"]["syncPolicy"]["automated"]["enabled"] = True
            app_config["spec"]["syncPolicy"]["automated"]["prune"] = True
            app_config["spec"]["syncPolicy"]["automated"]["selfHeal"] = True
            logger.debug(app_config["spec"])
        else:
            logger.info("disabling auto sync")
            if "syncPolicy" not in app_config["spec"]:
                app_config["spec"]["syncPolicy"] = {}
            if "automated" not in app_config["spec"]["syncPolicy"]:
                app_config["spec"]["syncPolicy"]["automated"] = {}
            # Use enabled=false instead of deleting the automated section
            app_config["spec"]["syncPolicy"]["automated"]["enabled"] = False
            logger.debug(app_config["spec"])

        logger.info(f" app name {app_name}")

        response = requests.put(
            f"{token_manager.ARGOCD_API_URL}/applications/{app_name}?validate=false",
            headers=headers,
            data=json.dumps(app_config),
            timeout=10,
            verify=False
        )

        if response.status_code == 200:
            logger.success("Application patched successfully.")
        else:
            logger.error(
                f"Failed to patch the application. Status code: {response.status_code}, Response: {response.text}. Exiting program."
            )
            raise Exception(f"Failed to patch application '{app_name}'. Status code: {res.status_code}, Response: {res.text}")
        
        # Verify the patch worked
        res = requests.get(
            f"{token_manager.ARGOCD_API_URL}/applications/{app_name}",
            headers=headers,
            timeout=5,
            verify=False
        )

        if res.status_code != 200:
            logger.error(f"Failed to verify patch for application '{app_name}'. Status code: {res.status_code}. Exiting program.")
            raise Exception(f"Failed to verify patch for application '{app_name}'. Status code: {res.status_code}")

        sync_policy = res.json().get('spec', {}).get('syncPolicy', {})
        if sync_policy and 'automated' in sync_policy:
            logger.info(f"Auto-sync enabled: prune={sync_policy['automated'].get('prune')}, selfHeal={sync_policy['automated'].get('selfHeal')}")
        else:
            logger.info("Auto-sync is disabled (no syncPolicy.automated)")
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Network error while patching application: {e}. Exiting program.")
        raise Exception(f"Network error while patching application: {e}")
    except Exception as e:
        logger.error(f"Unexpected error while patching application: {e}. Exiting program.")
        raise Exception(f"Unexpected error while patching application: {e}")