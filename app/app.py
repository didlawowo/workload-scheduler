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
import requests
import json

# Configure FastAPI app
app = FastAPI()
# logger.add("my_app.log", rotation="100 MB")

logger.info("Starting the application...")
# Configuration for Kubernetes client
if os.getenv("KUBE_ENV") == "development":
    config.load_kube_config()  # For local development
else:
    config.load_incluster_config()  # For running inside a cluster
logger.info("Kubernetes configuration loaded.")


# Kubernetes API clients

apps_v1 = client.AppsV1Api()
logger.info("Kubernetes API clients initialized.")

# Protected namespaces and label criteria
protected_namespaces = [
    "kube-system",
    # "default",
    "kube-public",
    # "longhorn-system",
    # "keeper",
]
shutdown_label_selector = 'shutdown="false"'

templates = Jinja2Templates(directory="templates")


class Workloads(BaseModel):
    workloads: List[str]


ARGOCD_API_URL = os.getenv("ARGOCD_API_URL", "http://localhost:8080/api/v1")
USERNAME = os.getenv("ARGOCD_USERNAME", "admin")
PASSWORD = os.getenv("ARGOCD_PASSWORD", "admin")

headers = {
    "Content-Type": "application/json",
}


def get_argocd_session_token():
    """
    Authenticates with the Argo CD API using username and password to obtain a session token.
    """
    logger.info("Authenticating with Argo CD...")
    auth_payload = {"username": USERNAME, "password": PASSWORD}
    response = requests.post(
        f"{ARGOCD_API_URL}/session", headers=headers, data=json.dumps(auth_payload)
    )

    if response.status_code == 200:
        session_token = response.json()["token"]
        # logger.debug(f"Session token: {session_token}")
        logger.info("Successfully authenticated with Argo CD.")
        return session_token
    else:
        logger.error(
            f"Failed to authenticate with Argo CD. Status code: {response.status_code}, Response: {response.text}"
        )
        return None


@app.get("/manage-all/{mode}")
async def manage_all_deployments(mode: str) -> Dict[str, Any]:
    logger.info("Received request to manage all workloads.")
    logger.info(f"mode: {mode}")
    try:
        deployment = apps_v1.list_deployment_for_all_namespaces(watch=False)
        deployment_list = [
            {
                "namespace": d.metadata.namespace,
                "name": d.metadata.name,
                "replicas": d.status.replicas,
                "available_replicas": d.status.available_replicas,
                "ready_replicas": d.status.ready_replicas,
                "labels": d.metadata.labels,
            }
            for d in deployment.items
            if d.metadata.namespace not in protected_namespaces
            if "argocd.argoproj.io/instance" in d.metadata.labels
        ]

        daemonset = apps_v1.list_daemon_set_for_all_namespaces(watch=False)
        daemonset_list = [
            {
                "namespace": d.metadata.namespace,
                "name": d.metadata.name,
                "labels": d.metadata.labels,
            }
            for d in daemonset.items
            if d.metadata.namespace not in protected_namespaces
            if "argocd.argoproj.io/instance" in d.metadata.labels
        ]

        sts = apps_v1.list_stateful_set_for_all_namespaces(watch=False)
        sts_list = [
            {
                "namespace": s.metadata.namespace,
                "name": s.metadata.name,
                "replicas": s.status.replicas,
                "available_replicas": s.status.available_replicas,
                "ready_replicas": s.status.ready_replicas,
                "labels": s.metadata.labels,
            }
            for s in sts.items
            if s.metadata.namespace not in protected_namespaces
            if "argocd.argoproj.io/instance" in s.metadata.labels
        ]
        ##
        for ds in daemonset_list:
            if mode == "down":
                logger.info(
                    f"Scaling down daemonset '{ds['name']}' in namespace '{ds['namespace']}'"
                )

                await shutdown_app("daemonset", ds["namespace"], ds["name"])
            elif mode == "up":
                logger.info(
                    f"Scaling up daemonset '{ds['name']}' in namespace '{ds['namespace']}'"
                )
                await scale_up_app("daemonset", ds["namespace"], ds["name"])

        for deploy in deployment_list:
            if mode == "down":
                logger.info(
                    f"Scaling down deploy '{deploy['name']}' in namespace '{deploy['namespace']}'"
                )

                await shutdown_app("deploy", deploy["namespace"], deploy["name"])
            elif mode == "up":
                logger.info(
                    f"Scaling up deploy '{deploy['name']}' in namespace '{deploy['namespace']}'"
                )
                await scale_up_app("deploy", deploy["namespace"], deploy["name"])

        for sts in sts_list:
            if mode == "down":
                logger.info(
                    f"Scaling down StatefulSet '{sts['name']}' in namespace '{sts['namespace']}'"
                )

                await shutdown_app("sts", sts["namespace"], sts["name"])
            elif mode == "up":
                logger.info(
                    f"Scaling up StatefulSet '{sts['name']}' in namespace '{sts['namespace']}'"
                )
                await scale_up_app("sts", sts["namespace"], sts["name"])
        # For simplicity, this example responds with a success message regardless of individual failures
        return {
            "message": "Bulk action to scale down deployments initiated. Check logs for individual action results."
        }
    except Exception as e:
        logger.error(f"Error while scaling down all workload Error: {e}")


@app.get("/shutdown/{resource_type}/{namespace}/{name}")
async def shutdown_app(resource_type: str, namespace: str, name: str) -> Dict[str, Any]:
    """
    shutdown the specified Deployment, considering protected namespaces and labels.
    """

    # Authenticate and get session token
    session_token = get_argocd_session_token()
    if session_token is None:
        logger.error("Authentication failed. Cannot proceed with scaling operation.")
        return

    # Check if the namespace is protected
    if namespace in protected_namespaces:
        return {
            "status": "error",
            "message": f"Namespace '{namespace}' is protected and cannot be modified.",
        }
    # logger.info(f"Shutdown Deployment '{name}' in namespace '{namespace}'")
    # Fetch the Deployment to check its labels
    if resource_type == "deploy":
        try:
            c = apps_v1.read_namespaced_deployment(name, namespace)
        except client.exceptions.ApiException as e:
            return {"status": "error", "message": str(e)}

        # Check if the Deployment has the shutdown protection label
        if shutdown_label_selector in c.metadata.labels:
            return {
                "status": "error",
                "message": f"Deployment '{name}' in namespace '{namespace}' is protected  ",
            }
    elif resource_type == "sts":
        try:
            c = apps_v1.read_namespaced_stateful_set(name, namespace)
        except client.exceptions.ApiException as e:
            return {"status": "error", "message": str(e)}

        # Check if the Deployment has the shutdown protection label
        if shutdown_label_selector in c.metadata.labels:
            return {
                "status": "error",
                "message": f"StatefulSet '{name}' in namespace '{namespace}' is protected  ",
            }
    elif resource_type == "ds":
        try:
            c = apps_v1.read_namespaced_daemon_set(name, namespace)
        except client.exceptions.ApiException as e:
            return {"status": "error", "message": str(e)}

        # Check if the Deployment has the shutdown protection label
        if shutdown_label_selector in c.metadata.labels:
            return {
                "status": "error",
                "message": f"DaemonSet '{name}' in namespace '{namespace}' is protected  ",
            }
    # logger.debug(c.metadata.labels)
    # patch the Deployment
    try:
        application_name = c.metadata.labels["argocd.argoproj.io/instance"]
        # Step 1: Disable auto-sync
        logger.info(f"Disabling auto-sync... for application '{application_name}'")
        patch_argocd_application(
            token=session_token,
            name=application_name,
            enable_auto_sync=False,
            namespace=namespace,
        )
        logger.success(
            f"Auto-sync disabled for application '{application_name}'. Proceeding with scaling down the Deployment."
        )
        # Define the patch to scale the Deployment

        body = {"spec": {"replicas": 0}}
        body_ds = {
            "spec": {"template": {"spec": {"nodeSelector": {"non-existing": "true"}}}}
        }
        if resource_type == "deploy":
            apps_v1.patch_namespaced_deployment_scale(
                name=name, namespace=namespace, body=body
            )
        elif resource_type == "sts":
            # Define the patch to scale the Sts

            apps_v1.patch_namespaced_stateful_set_scale(
                name=name, namespace=namespace, body=body
            )
        elif resource_type == "ds":
            # Define the patch to scale the Sts

            apps_v1.patch_namespaced_daemon_set(
                name=name, namespace=namespace, body=body_ds
            )
            # logger.debug(res)
        logger.info(
            f"{resource_type} '{name}' in namespace '{namespace}' has been shutdown  "
        )
        return {
            "status": "success",
            "message": f"{resource_type} '{name}' in namespace '{namespace}' has been shutdown.",
        }

    except client.exceptions.ApiException as e:
        logger.error(e)
        return {"status": "error", "message": str(e)}


@app.get("/up/{resource_type}/{namespace}/{name}")
async def scale_up_app(resource_type: str, namespace: str, name: str) -> Dict[str, Any]:
    """
    scale up the specified Deployment, considering protected namespaces and labels.
    """
    logger.info(f"Scaling up {resource_type} '{name}' in namespace '{namespace}'")
    # Authenticate and get session token
    session_token = get_argocd_session_token()
    if session_token is None:
        logger.error("Authentication failed. Cannot proceed with scaling operation.")
        return None

    if resource_type == "deploy":
        try:
            c = apps_v1.read_namespaced_deployment(name, namespace)
            logger.success("scaled up deployment")
        except client.exceptions.ApiException as e:
            return {"status": "error", "message": str(e)}

    elif resource_type == "sts":
        try:
            c = apps_v1.read_namespaced_stateful_set(name, namespace)
            logger.success("scaled up sts")
        except client.exceptions.ApiException as e:
            return {"status": "error", "message": str(e)}

    elif resource_type == "ds":
        try:
            c = apps_v1.read_namespaced_daemon_set(name=name, namespace=namespace)
            logger.success("scaled up ds")

        except client.exceptions.ApiException as e:
            return {"status": "error", "message": str(e)}

    # restore auto-sync
    try:
        application_name = c.metadata.labels["argocd.argoproj.io/instance"]
        # Step 1: Disable auto-sync
        logger.info(f"Enabling auto-sync for application '{application_name}'")
        patch_argocd_application(
            token=session_token,
            name=application_name,
            enable_auto_sync=True,
            namespace=namespace,
        )
        logger.success(
            f"Auto-sync enabled for application '{application_name}'. Proceeding with scaling down the Deployment."
        )
        # Define the patch to scale the Deployment
        body = {"spec": {"replicas": 1}}
        if resource_type == "deploy":
            apps_v1.patch_namespaced_deployment_scale(
                name=name, namespace=namespace, body=body
            )
        elif resource_type == "sts":
            # Define the patch to scale the Sts

            apps_v1.patch_namespaced_stateful_set_scale(
                name=name, namespace=namespace, body=body
            )
        elif resource_type == "ds":
            logger.info("scaling up ds")
            body_ds = {"spec": {"template": {"spec": {"nodeSelector": None}}}}
            apps_v1.patch_namespaced_daemon_set(
                name=name, namespace=namespace, body=body_ds
            )
            # logger.debug(res)
        return {
            "status": "success",
            "message": f"{resource_type} '{name}' in namespace '{namespace}' has been scaled up",
        }
    except client.exceptions.ApiException as e:
        logger.error(e)
        return {"status": "error", "message": str(e)}


def patch_argocd_application(token, namespace, name, enable_auto_sync):
    """
    Send a PATCH request to modify an Argo CD application.

    Parameters:
    - token (str): Authentication token for Argo CD.
    - app_namespace (str): The namespace of the application.
    - app_name (str): The name of the application.
    - enable_auto_sync (bool): Whether to enable or disable auto-sync.

    """
    # Example usage
    PATCH_TYPE = "merge"  # Assuming Argo CD supports standard Kubernetes patch types

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    res = requests.get(f"{ARGOCD_API_URL}/applications/{name}", headers=headers)
    app_config = res.json()
    # app_config.setdefault("spec", {}).setdefault("syncPolicy", {})
    logger.debug(app_config["spec"])
    if not enable_auto_sync:
        logger.info("disabling auto sync")
        # app_config["spec"]["syncPolicy"]["automated"] = {}
        app_config["spec"]["syncPolicy"].pop("automated", None)
        logger.debug(app_config["spec"])
    if enable_auto_sync:
        logger.info("enabling auto sync")
        app_config["spec"]["syncPolicy"]["automated"] = {
            "prune": True,
            "selfHeal": True,
        }

        # Prepare the payload for the PATCH request
    patch_payload = {"spec": {"syncPolicy": app_config["spec"]["syncPolicy"]}}

    payload = {
        "appNamespace": "kube-infra",
        "name": name,
        # "namespace": "kube-infra",
        "patch": json.dumps(patch_payload),
        "patchType": PATCH_TYPE,
        "project": app_config["spec"]["project"],
    }
    # logger.debug("check list app")
    logger.info(f" app name {name}")

    logger.debug(f"patch content {payload}")
    response = requests.patch(
        f"{ARGOCD_API_URL}/applications/{name}",
        headers=headers,
        data=json.dumps(payload),
    )

    if response.status_code == 200:
        logger.success("Application patched successfully.")
        logger.debug(response.json())
    else:
        logger.error(
            f"Failed to patch the application. Status code: {response.status_code}, Response: {response.text}"
        )
    res = requests.get(f"{ARGOCD_API_URL}/applications/{name}", headers=headers)
    logger.info(f"policy {res.json()['spec']['syncPolicy']}")


@app.get("/", response_class=HTMLResponse)
async def status(request: Request):
    """
    Fetches all Deployments / Sts and renders them using a Jinja2 template.
    """
    logger.info("Fetching Deployments and StatefulSets...")
    deployment = apps_v1.list_deployment_for_all_namespaces(watch=False)
    deployment_list = [
        {
            "namespace": d.metadata.namespace,
            "name": d.metadata.name,
            "replicas": d.status.replicas,
            "available_replicas": d.status.available_replicas,
            "ready_replicas": d.status.ready_replicas,
            "labels": d.metadata.labels,
        }
        for d in deployment.items
        if d.metadata.namespace not in protected_namespaces
        if "argocd.argoproj.io/instance" in d.metadata.labels
    ]

    sts = apps_v1.list_stateful_set_for_all_namespaces(watch=False)
    sts_list = [
        {
            "namespace": s.metadata.namespace,
            "name": s.metadata.name,
            "replicas": s.status.replicas,
            "available_replicas": s.status.available_replicas,
            "ready_replicas": s.status.ready_replicas,
            "labels": s.metadata.labels,
        }
        for s in sts.items
        if s.metadata.namespace not in protected_namespaces
        if "argocd.argoproj.io/instance" in s.metadata.labels
    ]

    daemonset = apps_v1.list_daemon_set_for_all_namespaces(watch=False)
    ds_list = [
        {
            "namespace": ds.metadata.namespace,
            "name": ds.metadata.name,
            "labels": ds.metadata.labels,
        }
        for ds in daemonset.items
        if ds.metadata.namespace not in protected_namespaces
        # if "argocd.argoproj.io/instance" in ds.metadata.labels
    ]
    # write result to filesystem
    with open("deployment.json", "w") as f:
        json.dump(deployment_list, f)
    with open("sts.json", "w") as f:
        json.dump(sts_list, f)
    with open("ds.json", "w") as f:
        json.dump(ds_list, f)

    logger.info(
        f"Deployments: {len(deployment_list)}, StatFulSets: {len(sts_list)}, DaemonSets: {len(ds_list)}"
    )
    # Render the template with the list of Deployments
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "deploy": deployment_list, "sts": sts_list, "ds": ds_list},
    )


@app.get("/list-deployments")
async def list_all_deployments():
    """
    Returns the status of all Deployments in all namespaces.
    """
    try:
        deployments = apps_v1.list_deployment_for_all_namespaces().items
        data = []
        for d in deployments:
            status = {
                "namespace": d.metadata.namespace,
                "name": d.metadata.name,
                "replicas": d.status.replicas,
                "available_replicas": d.status.available_replicas,
                "ready_replicas": d.status.ready_replicas,
                "labels": d.metadata.labels,
            }
            data.append(status)
        return {"status": "success", "data": data}
    except client.exceptions.ApiException as e:
        return {"status": "error", "message": str(e)}


@app.get("/live")
def live():
    return {"status": "ok"}


@app.get("/health")
def list_all_sts():
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

    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
