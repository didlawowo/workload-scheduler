import asyncio
import platform
from fastapi import FastAPI, Request
from loguru import logger
import os
from starlette.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import json
from icecream import ic
from pydantic import BaseModel
from typing import List
import sys
import uvicorn
import warnings
from api.scheduler import scheduler
from api.workload import workload, health_route
from core.kub_list import list_all_daemonsets, list_all_deployments, list_all_sts
from utils.config import protected_namespaces
from utils.helpers import apps_v1, core_v1
from core.scheduler_engine import SchedulerEngine
from core.dbManager import DatabaseManager

os.environ["TZ"] = "Europe/Paris"
log_level = os.getenv("LOG_LEVEL", "INFO")
logger.remove()
logger.add(sys.stderr, level=log_level)

def formatter(record):
    """
    Fonction de formatage personnalisée pour structurer les logs Loguru de manière compatible avec Datadog.
    Cette fonction transforme directement le record en une chaîne JSON sans utiliser de format intermédiaire.
    """
    # Création de la structure de log directement à partir des données du record
    log_data = {
        "timestamp": record["time"].timestamp() * 1000,
        "level": record["level"].name,
        "message": record["message"],
        "service": "workload-scheduler",
        "logger": {
            "name": record["name"],
            "method": record["function"],
            "file": record["file"].name,
            "line": record["line"],
        },
        "process": {"pid": record["process"].id, "thread_name": record["thread"].name},
    }

    return json.dumps(log_data)


# Suppression des handlers existants pour éviter tout conflit
logger.remove()

# Ajout du nouveau handler avec le formateur personnalisé
# Notez l'utilisation de format="{message}" qui laisse notre formateur gérer la structure complète
logger.add(
    sys.stdout,
    format="{message}",  # Format minimal
    serialize=False,  # Désactivation de la sérialisation automatique
    colorize=False,  # Désactivation de la coloration pour éviter les caractères d'échappement
    catch=True,  # Capture les erreurs de logging
)

# Configuration du handler pour utiliser notre formateur
logger = logger.patch(lambda record: record.update(message=formatter(record)))

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
scheduler_engine = SchedulerEngine(db_manager=db, check_interval=60)

logger.info("Starting the application...")


def custom_fallback(feature_name: str, context: dict) -> bool:
    return False

if os.getenv("UNLEASH_API_URL"):
    from UnleashClient import UnleashClient
    logger.info("Unleash client initialized.")
    unleashClient = UnleashClient(
        url=os.getenv("UNLEASH_API_URL"),
        app_name="workload-scheduler",
        custom_headers={"Authorization": os.getenv("UNLEASH_API_TOKEN")},
    )
    warnings.filterwarnings("ignore", category=UserWarning, module="unleash")

    unleashClient.initialize_client()
    unleashClient.is_enabled("debug", fallback_function=custom_fallback)



# Get the version from the environment variable
version = "2.3.2"  #
logger.info(f"Version: {version}")

templates_dir = os.path.join(BASE_DIR, "templates")
templates = Jinja2Templates(directory=templates_dir)

class Workloads(BaseModel):
    workloads: List[str]


# argo_session_token = get_argocd_session_token()

# Déterminer l'environnement (développement ou production)
is_dev = os.environ.get("APP_ENV", "development").lower() == "development"

async def init_database():
    """Initialise la base de données et stocke les UIDs des workloads"""
    logger.info("Initializing database...")

    await db.create_table()
    logger.success("Database created and tables initialized.")

    deployment_list = list_all_deployments(apps_v1, core_v1, protected_namespaces)
    sts_list = list_all_sts(apps_v1, core_v1, protected_namespaces)
    ds_list = list_all_daemonsets(apps_v1, core_v1, protected_namespaces)

    logger.success(
        f"Deployments: {len(deployment_list)}, StatFulSets: {len(sts_list)}, DaemonSets: {len(ds_list)}"
    )

    for dep in deployment_list:
        await db.store_uid(dep.get("uid"), dep.get('name'))
    for sts in sts_list:
        await db.store_uid(sts.get("uid"), sts.get('name'))
    for ds in ds_list:
        await db.store_uid(ds.get("uid"), ds.get('name'))
    logger.success("UIDs stored in database.")

# Démarrer le scheduler lors du démarrage de l'application
@app.on_event("startup")
async def startup_event():
    await init_database()
    asyncio.create_task(scheduler_engine.start())
    logger.info("Scheduler engine started in background")

# Arrêter proprement le scheduler lors de l'arrêt de l'application
@app.on_event("shutdown")
async def shutdown_event():
    await scheduler_engine.stop()
    logger.info("Scheduler engine stopped")


@app.get("/", response_class=HTMLResponse)
def status(request: Request):
    """
    Fetches all Deployments /   and renders them using a Jinja2 template.
    """
    logger.info("Fetching Deployments, Daemonets and StatefulSets...")
    deployment_list = list_all_deployments(apps_v1, core_v1, protected_namespaces)
    sts_list = list_all_sts(apps_v1, core_v1, protected_namespaces)
    ds_list = list_all_daemonsets(apps_v1, core_v1, protected_namespaces)

    logger.success(
        f"Deployments: {len(deployment_list)}, StatFulSets: {len(sts_list)}, DaemonSets: {len(ds_list)},  "
    )
    # Render the template with the list of Deployments
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "deploy": deployment_list,
            "sts": sts_list,
            "ds": ds_list,
            # Use the version in your code
            "version": version,
        },
    )


# Run the application
async def main():
    logger.info("Starting Workload Scheduler...")
    logger.info("🚀 Application ready.")

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