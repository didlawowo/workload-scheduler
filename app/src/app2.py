from fastapi import FastAPI, Request
from kubernetes import client, config
from loguru import logger
import os
from starlette.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import List
import uvicorn
from typing import Any, Dict

# Configure FastAPI app
app = FastAPI()
logger.add("my_app.log", rotation="100 MB")

# Configuration for Kubernetes client
if os.getenv("KUBE_ENV") == "development":
    config.load_kube_config()  # For local development
else:
    config.load_incluster_config()  # For running inside a cluster

# Kubernetes API clients

apps_v1 = client.AppsV1Api()

# Protected namespaces and label criteria
protected_namespaces = ["kube-system", "default", "kube-public"]
shutdown_label_selector = 'shutdown!="false"'

templates = Jinja2Templates(directory="templates")


class Workloads(BaseModel):
    workloads: List[str]


@app.post("/down-all")
async def scale_down_deployments(request: Request, workloads: Workloads):
    for workload in workloads.workloads:
        # Expected workload format: "deploymentName_namespace"
        details = workload.split("_")
        logger.debug(f"Scaling down workload: {workload}")
        if len(details) != 2:
            logger.error(f"Invalid workload format: {workload}")
            continue  # Skip invalidly formatted workloads

        deployment_name, namespace = details
        try:
            # Check for protected namespaces or other criteria here
            patch_body = {"spec": {"replicas": 0}}
            response = apps_v1.patch_namespaced_deployment_scale(
                deployment_name, namespace, patch_body
            )
            logger.info(
                f"Scaled down deployment: {deployment_name} in namespace: {namespace} successfully."
            )
        except client.exceptions.ApiException as e:
            logger.error(
                f"Failed to scale down deployment: {deployment_name} in namespace: {namespace}. Error: {e}"
            )
            # Decide how to handle individual errors; accumulate them or fail at first error

    # For simplicity, this example responds with a success message regardless of individual failures
    return {
        "message": "Bulk action to scale down deployments initiated. Check logs for individual action results."
    }


@app.get("/manage/{resource_type}/{namespace}/{name}/{number}")
async def manage_replica_set(
    resource_type: str, namespace: str, name: str, number: int
) -> Dict[str, Any]:
    """

    Scales the specified Deployment, considering protected namespaces and labels.
    """
    if number < 0:
        return {"status": "error", "message": "Replica count cannot be less than 0"}
    if number == 0:
        word = "shutdown"
    if number >= 1:
        word = "scaleUp"

    # Check if the namespace is protected
    if namespace in protected_namespaces:
        return {
            "status": "error",
            "message": f"Namespace '{namespace}' is protected and cannot be modified.",
        }
    logger.info(
        f"Scaling Deployment '{name}' in namespace '{namespace}' to '{number}'."
    )
    # Fetch the Deployment to check its labels
    if resource_type == "deploy":
        try:
            deployment = apps_v1.read_namespaced_deployment(name, namespace)
        except client.exceptions.ApiException as e:
            return {"status": "error", "message": str(e)}

        # Check if the Deployment has the shutdown protection label
        if shutdown_label_selector in deployment.metadata.labels:
            return {
                "status": "error",
                "message": f"Deployment '{name}' in namespace '{namespace}' is protected from '{word}'.",
            }
    elif resource_type == "sts":
        try:
            deployment = apps_v1.read_namespaced_stateful_set(name, namespace)
        except client.exceptions.ApiException as e:
            return {"status": "error", "message": str(e)}

        # Check if the Deployment has the shutdown protection label
        if shutdown_label_selector in deployment.metadata.labels:
            return {
                "status": "error",
                "message": f"StatefulSet '{name}' in namespace '{namespace}' is protected from '{word}'.",
            }
    # patch the Deployment
    try:
        if resource_type == "deploy":
            # Define the patch to scale the Deployment
            body = {"spec": {"replicas": number}}
            res = apps_v1.patch_namespaced_deployment_scale(
                name=name, namespace=namespace, body=body
            )
            logger.debug(res)
            logger.info(
                f"Deployment '{name}' in namespace '{namespace}' has been scaled to '{number}'."
            )
            return {
                "status": "success",
                "message": f"Deployment '{name}' in namespace '{namespace}' has been scaled to '{number}'.",
            }
        elif resource_type == "sts":
            # Define the patch to scale the Sts
            body = {"spec": {"replicas": number}}
            res = apps_v1.patch_namespaced_stateful_set_scale(
                name=name, namespace=namespace, body=body
            )
            logger.debug(res)
            logger.info(
                f"StatefulSet '{name}' in namespace '{namespace}' has been scaled to '{number}'."
            )
            return {
                "status": "success",
                "message": f"StatefulSet '{name}' in namespace '{namespace}' has been scaled to '{number}'.",
            }
    except client.exceptions.ApiException as e:
        logger.error(e)
        return {"status": "error", "message": str(e)}


@app.get("/status", response_class=HTMLResponse)
async def status(request: Request):
    """
    Fetches all Deployments / Sts and renders them using a Jinja2 template.
    """

    deployment = apps_v1.list_deployment_for_all_namespaces(watch=False)
    deployment_list = [
        {
            "namespace": d.metadata.namespace,
            "name": d.metadata.name,
            "replicas": d.status.replicas,
            "available_replicas": d.status.available_replicas,
            "ready_replicas": d.status.ready_replicas,
        }
        for d in deployment.items
    ]
    sts = apps_v1.list_stateful_set_for_all_namespaces(watch=False)
    sts_list = [
        {
            "namespace": s.metadata.namespace,
            "name": s.metadata.name,
            "replicas": s.status.replicas,
            "available_replicas": s.status.available_replicas,
            "ready_replicas": s.status.ready_replicas,
        }
        for s in sts.items
    ]
    # filter rs.status.replicas > 0
    # rs_list = [rs for rs in rs_list if rs["replicas"] > 0]

    # Render the template with the list of Deployments
    return templates.TemplateResponse(
        "index.html", {"request": request, "deploy": deployment_list, "sts": sts_list}
    )


@app.get("/list-rs")
async def list_all_Deployments():
    """
    Returns the status of all Deployments in all namespaces.
    """
    try:
        replica_sets = apps_v1.list_replica_set_for_all_namespaces().items
        data = []
        for rs in replica_sets:
            status = {
                "namespace": rs.metadata.namespace,
                "name": rs.metadata.name,
                "replicas": rs.status.replicas,
                "available_replicas": rs.status.available_replicas,
                "ready_replicas": rs.status.ready_replicas,
                "labels": rs.metadata.labels,
            }
            data.append(status)
        return {"status": "success", "data": data}
    except client.exceptions.ApiException as e:
        return {"status": "error", "message": str(e)}


@app.get("/list-deployments")
async def list_all_deployments():
    """
    Returns the status of all Deployments in all namespaces.
    """
    try:
        replica_sets = apps_v1.list_deployment_for_all_namespaces().items
        data = []
        for rs in replica_sets:
            status = {
                "namespace": rs.metadata.namespace,
                "name": rs.metadata.name,
                "replicas": rs.status.replicas,
                "available_replicas": rs.status.available_replicas,
                "ready_replicas": rs.status.ready_replicas,
                "labels": rs.metadata.labels,
            }
            data.append(status)
        return {"status": "success", "data": data}
    except client.exceptions.ApiException as e:
        return {"status": "error", "message": str(e)}


@app.get("/list-sts")
async def list_all_sts():
    """
    Returns the status of all sts in all namespaces.
    """
    try:
        replica_sets = apps_v1.list_stateful_set_for_all_namespaces().items
        data = []
        for rs in replica_sets:
            status = {
                "namespace": rs.metadata.namespace,
                "name": rs.metadata.name,
                "replicas": rs.status.replicas,
                "available_replicas": rs.status.available_replicas,
                "ready_replicas": rs.status.ready_replicas,
                "labels": rs.metadata.labels,
            }
            data.append(status)
        return {"status": "success", "data": data}
    except client.exceptions.ApiException as e:
        return {"status": "error", "message": str(e)}


# Run the application
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app2:app", host="0.0.0.0", port=8000, reload=True)
