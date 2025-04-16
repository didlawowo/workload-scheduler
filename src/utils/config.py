from kubernetes import client, config
import os
from loguru import logger


# Protected namespaces and label criteria
protected_namespaces = [
    "kube-system",
    # "default",
    "kube-public",
    "longhorn-system",
    # "keeper",
]
shutdown_label_selector = 'shutdown="false"'


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
    apps_v1 = client.AppsV1Api()
    core_v1 = client.CoreV1Api()
    logger.info("Kubernetes API clients initialized.")
    
    return apps_v1, core_v1

# Initialize clients
apps_v1, core_v1 = initialize_kubernetes()