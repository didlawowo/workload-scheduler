import requests
import json
from loguru import logger
import os

ARGOCD_API_URL = os.getenv("ARGOCD_API_URL", "https://localhost:8080/api/v1")
USERNAME = os.getenv("ARGOCD_USERNAME", "admin")
PASSWORD = os.getenv("ARGOCD_PASSWORD", "admin")

headers = {
    "Content-Type": "application/json",
}

@logger.catch
def get_argocd_session_token():
    """
    Authenticates with the Argo CD API using username and password to obtain a session token.
    """
    logger.info("Authenticating with Argo CD...")
    auth_payload = {"username": USERNAME, "password": PASSWORD}
    response = requests.post(
        f"{ARGOCD_API_URL}/session",
        headers=headers,
        data=json.dumps(auth_payload),
        timeout=5,
    )

    if response.status_code == 200:
        session_token = response.json()["token"]
        # logger.debug(f"Session token: {session_token}")
        logger.success("Successfully authenticated with Argo CD.")
        return session_token

    logger.error(
        f"Failed to authenticate with Argo CD. Status code: {response.status_code}, Response: {response.text}"
    )
    return None


def patch_argocd_application(token, app_name, enable_auto_sync):
    """
    Send a PATCH request to modify an Argo CD application.

    Parameters:
    - token (str): Authentication token for Argo CD.
    - app_namespace (str): The namespace of the application.
    - app_name (str): The name of the application.
    - enable_auto_sync (bool): Whether to enable or disable auto-sync.

    """
    # Example usage

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    res = requests.get(
        f"{ARGOCD_API_URL}/applications/{app_name}", headers=headers, timeout=3
    )
    app_config = res.json()
    # app_config.setdefault("spec", {}).setdefault("syncPolicy", {})
    logger.debug(app_config["spec"])
    if not enable_auto_sync:
        logger.info("disabling auto sync")
        # app_config["spec"]["syncPolicy"]["automated"] = {}
        app_config["spec"]["syncPolicy"]["automated"] = None
        logger.debug(app_config["spec"])
    if enable_auto_sync:
        logger.info("enabling auto sync")
        app_config["spec"]["syncPolicy"]["automated"] = {
            "prune": True,
            "selfHeal": True,
        }

    logger.info(f" app name {app_name}")

    # logger.debug(f"patch content {app_config}")
    response = requests.put(
        f"{ARGOCD_API_URL}/applications/{app_name}?validate=false",
        headers=headers,
        data=json.dumps(app_config),
        timeout=10,
    )

    if response.status_code == 200:
        logger.success("Application patched successfully.")
        # logger.debug(response.json())
    else:
        logger.error(
            f"Failed to patch the application. Status code: {response.status_code}, Response: {response.text}"
        )
    res = requests.get(
        f"{ARGOCD_API_URL}/applications/{app_name}", headers=headers, timeout=5
    )
    logger.info(f"policy {res.json()['spec']['syncPolicy']}")

