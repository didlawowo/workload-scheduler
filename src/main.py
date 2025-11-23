import asyncio
import os
import platform
import warnings
from typing import List

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from icecream import ic
from loguru import logger
from pydantic import BaseModel
from starlette.templating import Jinja2Templates

from api.scheduler import scheduler
from api.workload import health_route, workload
from core.dbManager import DatabaseManager
from core.kub_list import list_all_daemonsets, list_all_deployments, list_all_sts
from scheduler_engine import SchedulerEngine
from utils.argocd import ArgoTokenManager
from utils.config import protected_labels, protected_namespaces
from utils.helpers import apps_v1, core_v1
from utils.logging_config import configure_logger

os.environ["TZ"] = "Europe/Paris"

# Configure logger with JSON format for Datadog
configure_logger(service_name="workload-scheduler", component="api")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Configure FastAPI app
app = FastAPI()
static_dir = os.path.join(BASE_DIR, "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")
app.include_router(router=scheduler)
app.include_router(router=workload)
app.include_router(router=health_route)

# Création d'une instance de DatabaseManager
db = DatabaseManager()

# Initialiser le scheduler avec un intervalle personnalisé (en secondes)
scheduler_engine = SchedulerEngine(check_interval=60)

logger.info("Starting the application...")


def custom_fallback(feature_name: str, context: dict) -> bool:
    return False

unleash_api_url = os.getenv("UNLEASH_API_URL")
if unleash_api_url:
    from UnleashClient import UnleashClient
    logger.info("Unleash client initialized.")
    unleashClient = UnleashClient(
        url=unleash_api_url,
        app_name="workload-scheduler",
        custom_headers={"Authorization": os.getenv("UNLEASH_API_TOKEN", "")},
    )
    warnings.filterwarnings("ignore", category=UserWarning, module="unleash")

    unleashClient.initialize_client()
    unleashClient.is_enabled("debug", fallback_function=custom_fallback)



# Get the version from the environment variable
version = "2.4.1"  #
logger.info(f"Version: {version}")

templates_dir = os.path.join(BASE_DIR, "templates")
templates = Jinja2Templates(directory=templates_dir)

class Workloads(BaseModel):
    workloads: List[str]

token_manager = ArgoTokenManager()

async def init_argocd_token():
    """Initialise le token ArgoCD global avec gestion d'erreur"""
    if os.getenv("ARGOCD_API_URL"):
        try:
            logger.info("Initializing ArgoCD session token...")
            token = token_manager.get_token()
            
            if not token:
                logger.error("Failed to obtain ArgoCD token. Check credentials or ArgoCD server availability.")

            logger.success("ArgoCD session token initialized.")
        except Exception as e:
            logger.error(f"Error initializing ArgoCD token: {str(e)}")
            logger.warning("ArgoCD integration will not be available.")
    else:
        logger.warning("ARGOCD_API_URL not set, skipping token initialization")

# Déterminer l'environnement (développement ou production)
is_dev = os.getenv("APP_ENV", "development").lower() == "development"

async def init_database():
    """Initialise la base de données et stocke les UIDs des workloads"""
    try:
        logger.info("Initializing database...")
        
        await db.create_table()
        logger.success("Database created and tables initialized.")
        
        deployment_list = list_all_deployments(apps_v1, core_v1, protected_namespaces, protected_labels)
        sts_list = list_all_sts(apps_v1, core_v1, protected_namespaces, protected_labels)
        ds_list = list_all_daemonsets(apps_v1, core_v1, protected_namespaces, protected_labels)

        # Vérifier que les listes sont bien des listes et non des dicts d'erreur
        if isinstance(deployment_list, dict) or isinstance(sts_list, dict) or isinstance(ds_list, dict):
            logger.error("Error fetching workloads from Kubernetes API")
            return

        logger.success(
            f"Deployments: {len(deployment_list)}, StatFulSets: {len(sts_list)}, DaemonSets: {len(ds_list)}"
        )

        for dep in deployment_list:
            uid = dep.get("uid")
            name = dep.get("name")
            if uid and name and isinstance(uid, str) and isinstance(name, str):
                await db.store_uid(uid, name)
        for sts in sts_list:
            uid = sts.get("uid")
            name = sts.get("name")
            if uid and name and isinstance(uid, str) and isinstance(name, str):
                await db.store_uid(uid, name)
        for ds in ds_list:
            uid = ds.get("uid")
            name = ds.get("name")
            if uid and name and isinstance(uid, str) and isinstance(name, str):
                await db.store_uid(uid, name)
        logger.success("UIDs stored in database.")
    except Exception as e:
        logger.error(f"Error initializing database: {str(e)}")
        raise


@app.get("/", response_class=HTMLResponse)
def status(request: Request):
    """
    Fetches all Deployments /   and renders them using a Jinja2 template.
    """
    try:
        logger.info("Fetching Deployments, Daemonets and StatefulSets...")
        deployment_list = list_all_deployments(apps_v1, core_v1, protected_namespaces, protected_labels)
        sts_list = list_all_sts(apps_v1, core_v1, protected_namespaces, protected_labels)
        ds_list = list_all_daemonsets(apps_v1, core_v1, protected_namespaces, protected_labels)
        
        logger.success(
            f"Deployments: {len(deployment_list)}, StatFulSets: {len(sts_list)}, DaemonSets: {len(ds_list)},  "
        )
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "deploy": deployment_list,
                "sts": sts_list,
                "ds": ds_list,
                "version": version,
            },
        )
    except Exception as e:
        logger.error(f"Error in status endpoint: {str(e)}")
        return HTMLResponse(
            content=f"<html><body><h1>Error</h1><p>An error occurred: {str(e)}</p></body></html>",
            status_code=500
        )


# Run the application
async def main():
    logger.info("🚀 Application starting.")
    await init_database()
    await init_argocd_token()

if __name__ == "__main__":
    if platform.system() == "Darwin":
        ic.enable()
    else:
        ic.disable()
    logger.info("🚀 Démarrage du script")
    try:
        asyncio.run(main())
        logger.info("Starting Workload Scheduler...")

        uvicorn_config = uvicorn.Config(
            app,
            host="0.0.0.0",
            port=8000,
            reload=is_dev,
            reload_dirs=["."]
        )

        server = uvicorn.Server(uvicorn_config)
        server.run()

        logger.success("Started Workload Scheduler...")
    except KeyboardInterrupt:
        logger.info("👋 Arrêt demandé par l'utilisateur")