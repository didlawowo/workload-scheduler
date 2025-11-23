"""
Configuration centralisée du logging pour Datadog.
Ce module configure loguru pour produire des logs au format JSON compatibles avec Datadog.
"""
import json
import os
import sys

from loguru import logger


def configure_logger(service_name: str = "workload-scheduler", component: str = "api"):
    """
    Configure le logger avec un format JSON compatible Datadog.

    Args:
        service_name: Nom du service pour Datadog
        component: Composant de l'application (api, scheduler, etc.)
    """
    # Récupérer le niveau de log depuis l'environnement
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    valid_log_levels = ["TRACE", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL"]

    if log_level not in valid_log_levels:
        print(f"Invalid LOG_LEVEL: {log_level}. Using INFO as default.")
        log_level = "INFO"

    def sink(message):
        """
        Custom sink pour formater les logs en JSON pour Datadog.
        """
        record = message.record
        log_data = {
            "timestamp": record["time"].timestamp() * 1000,
            "level": record["level"].name,
            "message": record["message"],
            "service": service_name,
            "component": component,
            "logger": {
                "name": record["name"],
                "method": record["function"],
                "file": record["file"].name,
                "line": record["line"],
            },
            "process": {
                "pid": record["process"].id,
                "thread_name": record["thread"].name
            },
        }

        # Ajouter les extras si présents
        if record["extra"]:
            log_data["extra"] = record["extra"]

        sys.stderr.write(json.dumps(log_data) + "\n")
        sys.stderr.flush()

    # Supprimer les handlers par défaut
    logger.remove()

    # Ajouter le handler avec custom sink
    logger.add(
        sink,
        level=log_level,
        colorize=False,
        catch=True,
    )

    logger.info(f"Logger configuré pour {service_name}/{component} avec niveau {log_level}")
