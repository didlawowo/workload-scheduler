from kubernetes import client, config
import os
from loguru import logger

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

# Initialize at module level so they can be imported directly
apps_v1, core_v1 = initialize_kubernetes()