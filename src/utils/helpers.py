import os
import httpx
from kubernetes import client, config
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential


# Initialize Kubernetes API clients
def initialize_kubernetes():
    """Initialize Kubernetes clients based on environment"""
    if os.getenv("KUBE_ENV") == "development":
        config.load_kube_config()  # For local development
        logger.info("Kubernetes local configuration loaded.")
    else:
        config.load_incluster_config()  # For running inside a cluster
        logger.info("Kubernetes in cluster configuration loaded.")
    
    # Create API clients
    apps_v1_api = client.AppsV1Api()
    core_v1_api = client.CoreV1Api()
    logger.info("Kubernetes API clients initialized.")
    return apps_v1_api, core_v1_api

# Initialize at module level, but skip in test mode
if os.getenv("TESTING") == "1":
    # In test mode, create None placeholders (tests should mock these)
    apps_v1 = None
    core_v1 = None
    logger.warning("Skipping Kubernetes initialization in test mode")
else:
    # Normal initialization for production/development
    apps_v1, core_v1 = initialize_kubernetes()

class RetryableAsyncClient(httpx.AsyncClient):
    """🔄 Client HTTP avec retry intégré"""

    def __init__(self, *args, **kwargs):
        # Assurons-nous que follow_redirects est activé par défaut
        if "follow_redirects" not in kwargs:
            kwargs["follow_redirects"] = True
        super().__init__(*args, **kwargs)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        reraise=True,
    )
    async def request(self, *args, **kwargs) -> httpx.Response:
        """Surcharge de la méthode request pour ajouter le retry"""
        try:
            # Assurons-nous que chaque requête suit les redirections
            if "follow_redirects" not in kwargs:
                kwargs["follow_redirects"] = True

            response = await super().request(*args, **kwargs)
            response.raise_for_status()
            return response

        except httpx.TimeoutException as e:
            logger.error(f"Request timed out: {e}")
            raise  # Relève l'exception pour que le retry puisse fonctionner

        except httpx.RequestError as e:
            logger.error(f"Request error: {e!s}")
            raise  # Relève l'exception pour que le retry puisse fonctionner

        except httpx.HTTPError as e:
            logger.error(f"❌ Erreur HTTP: {e}")
            if hasattr(e, "response") and e.response is not None:
                logger.error(f"Réponse: {e.response.text}")
            raise