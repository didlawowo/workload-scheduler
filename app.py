from fastapi import FastAPI, Request
from kubernetes import client, config
from loguru import logger
import os
from starlette.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from pydantic import BaseModel
from typing import List
import uvicorn
from typing import Any, Dict
import requests
import json
from UnleashClient import UnleashClient


# Configure FastAPI app
app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

logger.info("Starting the application...")
# Configuration for Kubernetes client
if os.getenv("KUBE_ENV") == "development":
    config.load_kube_config()  # For local development
else:
    config.load_incluster_config()  # For running inside a cluster
    logger.info("Kubernetes in cluster configuration loaded.")


def custom_fallback(feature_name: str, context: dict) -> bool:
    return False


unleashClient = UnleashClient(
    url=os.getenv("UNLEASH_API_URL"),
    app_name="workload-scheduler",
    custom_headers={"Authorization": os.getenv("UNLEASH_API_TOKEN")},
)

unleashClient.initialize_client()
unleashClient.is_enabled("debug", fallback_function=custom_fallback)


# Load environment variables from .envrc file
# load_dotenv(".envrc")

# Get the version from the environment variable
version = "2.2.0"  # Default to '2.0.0' if not found
logger.info(f"Version: {version}")
# Kubernetes API clients
apps_v1 = client.AppsV1Api()
core_v1 = client.CoreV1Api()
logger.info("Kubernetes API clients initialized.")

# Protected namespaces and label criteria
protected_namespaces = [
    "kube-system",
    # "default",
    "kube-public",
    "longhorn-system",
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
        logger.success("Successfully authenticated with Argo CD.")
        return session_token
    else:
        logger.error(
            f"Failed to authenticate with Argo CD. Status code: {response.status_code}, Response: {response.text}"
        )
        return None


argo_session_token = get_argocd_session_token()


@app.get("/manage-all/{mode}")
async def manage_all_deployments(mode: str) -> Dict[str, Any]:
    logger.info("Received request to manage all workloads.")
    logger.info(f"mode: {mode}")
    try:
        deployment_list = list_all_deployments
        sts_list = list_all_sts

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
            d = apps_v1.read_namespaced_deployment(name, namespace)
            application_name = d.metadata.labels["argocd.argoproj.io/instance"]

        except client.exceptions.ApiException as e:
            return {"status": "error", "message": str(e)}

        # Check if the Deployment has the shutdown protection label
        if shutdown_label_selector in d.metadata.labels:
            return {
                "status": "error",
                "message": f"Deployment '{name}' in namespace '{namespace}' is protected  ",
            }
    elif resource_type == "sts":
        try:
            sts = apps_v1.read_namespaced_stateful_set(name, namespace)
            application_name = sts.metadata.labels["argocd.argoproj.io/instance"]

        except client.exceptions.ApiException as e:
            return {"status": "error", "message": str(e)}

        # Check if the Deployment has the shutdown protection label
        if shutdown_label_selector in sts.metadata.labels:
            return {
                "status": "error",
                "message": f"StatefulSet '{name}' in namespace '{namespace}' is protected  ",
            }

    # logger.debug(c.metadata.labels)
    # patch the resources
    try:
        # Step 1: Disable auto-sync
        if resource_type != "ds":
            logger.info(f"Disabling auto-sync... for application '{application_name}'")
            patch_argocd_application(
                token=argo_session_token,
                app_name=application_name,
                enable_auto_sync=False,
            )
            logger.success(
                f"Auto-sync disabled for application '{application_name}'. Proceeding with scaling down the Deployment."
            )
            # Define the patch to scale the Deployment

            body = {"spec": {"replicas": 0}}

            if resource_type == "deploy":
                apps_v1.patch_namespaced_deployment_scale(
                    name=name, namespace=namespace, body=body
                )
            elif resource_type == "sts":
                apps_v1.patch_namespaced_stateful_set_scale(
                    name=name, namespace=namespace, body=body
                )

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
        # Step 1: enable auto-sync
        logger.info(f"Enabling auto-sync for application '{application_name}'")
        patch_argocd_application(
            token=argo_session_token,
            app_name=application_name,
            enable_auto_sync=True,
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
    res = requests.get(f"{ARGOCD_API_URL}/applications/{app_name}", headers=headers)
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
    )

    if response.status_code == 200:
        logger.success("Application patched successfully.")
        # logger.debug(response.json())
    else:
        logger.error(
            f"Failed to patch the application. Status code: {response.status_code}, Response: {response.text}"
        )
    res = requests.get(f"{ARGOCD_API_URL}/applications/{app_name}", headers=headers)
    logger.info(f"policy {res.json()['spec']['syncPolicy']}")


@app.get("/", response_class=HTMLResponse)
def status(request: Request):
    """
    Fetches all Deployments /   and renders them using a Jinja2 template.
    """
    logger.info("Fetching Deployments, Daemonets and StatefulSets...")
    deployment_list = list_all_deployments()
    sts_list = list_all_sts()
    ds_list = list_all_daemonsets()

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


@app.get("/delete-rs")
def delete_rs_zero():
    """
    Deletes all ReplicaSets with desired replicas set to 0.
    """
    try:
        namespaces = core_v1.list_namespace()
        deleted_replicasets = []

        for ns in namespaces.items:
            if ns.metadata.name not in protected_namespaces:
                replicasets = apps_v1.list_namespaced_replica_set(ns.metadata.name)
                for rs in replicasets.items:
                    if rs.spec.replicas == 0:
                        apps_v1.delete_namespaced_replica_set(
                            name=rs.metadata.name, namespace=rs.metadata.namespace
                        )
                        deleted_replicasets.append(
                            {
                                "name": rs.metadata.name,
                                "namespace": rs.metadata.namespace,
                            }
                        )

        logger.info(
            f"Deleted {len(deleted_replicasets)} ReplicaSets with 0 desired replicas"
        )
        return {"status": "success", "deleted_replicasets": len(deleted_replicasets)}
    except client.exceptions.ApiException as e:
        logger.error(f"Error deleting ReplicaSets: {str(e)}")
        return {"status": "error", "message": str(e)}


def list_all_daemonsets():
    """
    Returns the status of all DaemonSets in all namespaces, including pod information.
    """
    try:
        daemonsets = apps_v1.list_daemon_set_for_all_namespaces(watch=False)
        daemonset_list = []

        for ds in daemonsets.items:
            # Skip if not matching our criteria
            if (
                ds.metadata.labels is None
                or ds.metadata.namespace in protected_namespaces
            ):
                continue

            # Get pods directly - DaemonSets control pods directly (no ReplicaSet in between)
            pods = core_v1.list_namespaced_pod(ds.metadata.namespace).items

            pod_info = []

            for pod in pods:
                if pod.metadata.owner_references:
                    for owner in pod.metadata.owner_references:
                        if owner.kind == "DaemonSet" and owner.name == ds.metadata.name:
                            # Check for PVCs
                            has_pvc = any(
                                volume.persistent_volume_claim
                                for volume in pod.spec.volumes
                                if hasattr(volume, "persistent_volume_claim")
                            )

                            # Get resource requests and limits
                            resources = pod.spec.containers[0].resources
                            requests = (
                                resources.requests
                                if resources and resources.requests
                                else {}
                            )
                            limits = (
                                resources.limits
                                if resources and resources.limits
                                else {}
                            )

                            # Get node conditions if available
                            node_conditions = {}
                            if pod.spec.node_name:
                                try:
                                    node = core_v1.read_node(pod.spec.node_name)
                                    node_conditions = {
                                        cond.type: cond.status
                                        for cond in node.status.conditions
                                    }
                                except client.exceptions.ApiException:
                                    logger.warning(
                                        f"Could not fetch conditions for node {pod.spec.node_name}"
                                    )

                            pod_info.append(
                                {
                                    "name": pod.metadata.name,
                                    "node": pod.spec.node_name,
                                    "status": pod.status.phase,
                                    "has_pvc": has_pvc,
                                    "resource_requests": requests,
                                    "resource_limits": limits,
                                    "node_conditions": node_conditions,
                                    "start_time": pod.status.start_time.isoformat()
                                    if pod.status.start_time
                                    else None,
                                }
                            )
                            # logger.debug(pod_info)
                            break

            # Get DaemonSet-specific status
            status = {
                "desired_number_scheduled": ds.status.desired_number_scheduled,
                "current_number_scheduled": ds.status.current_number_scheduled,
                "number_ready": ds.status.number_ready,
                "updated_number_scheduled": ds.status.updated_number_scheduled,
                "number_available": ds.status.number_available
                if hasattr(ds.status, "number_available")
                else None,
                "number_misscheduled": ds.status.number_misscheduled,
            }

            daemonset_list.append(
                {
                    "namespace": ds.metadata.namespace,
                    "name": ds.metadata.name,
                    "labels": ds.metadata.labels,
                    "status": status,
                    "pods": pod_info,
                    "update_strategy": ds.spec.update_strategy.type
                    if ds.spec.update_strategy
                    else None,
                    "selector": ds.spec.selector.match_labels,
                }
            )

        return daemonset_list

    except client.exceptions.ApiException as e:
        return {"status": "error", "message": str(e)}


def list_all_deployments():
    """
    Returns the status of all Deployments in all namespaces, including pod information.
    """
    try:
        deployment = apps_v1.list_deployment_for_all_namespaces(watch=False)
        deployment_list = []
        logger.debug(f"{len(deployment.items)} deployments found ")

        for d in deployment.items:
            # Skip if not matching our criteria

            if (
                d.metadata.name == "workload-scheduler"
                or d.metadata.labels is None
                or d.metadata.namespace in protected_namespaces
                or "argocd.argoproj.io/instance" not in d.metadata.labels
            ):
                continue

            # Get ReplicaSets for this deployment
            replicasets = apps_v1.list_namespaced_replica_set(
                d.metadata.namespace,
                label_selector=",".join(
                    [f"{k}={v}" for k, v in d.spec.selector.match_labels.items()]
                ),
            )
            # logger.debug(f"{len(replicasets.items)} replicasets found ")
            # Find the active ReplicaSet(s)
            active_rs = []
            for rs in replicasets.items:
                if rs.metadata.owner_references:
                    for owner in rs.metadata.owner_references:
                        if owner.kind == "Deployment" and owner.name == d.metadata.name:
                            active_rs.append(rs)
                            break

            # Sort ReplicaSets by creation timestamp to get the most recent one
            active_rs.sort(key=lambda x: x.metadata.creation_timestamp, reverse=True)

            # Get pods
            pods = core_v1.list_namespaced_pod(d.metadata.namespace, watch=False).items

            pod_info = []

            for pod in pods:
                if pod.metadata.owner_references:
                    for owner in pod.metadata.owner_references:
                        # Check if pod belongs to one of our active ReplicaSets
                        if owner.kind == "ReplicaSet" and any(
                            rs.metadata.name == owner.name for rs in active_rs
                        ):
                            # Check for PVCs
                            has_pvc = any(
                                volume.persistent_volume_claim
                                for volume in pod.spec.volumes
                                if hasattr(volume, "persistent_volume_claim")
                            )

                            # Get resource requests and limits
                            resources = pod.spec.containers[0].resources
                            requests = (
                                resources.requests
                                if resources and resources.requests
                                else {}
                            )
                            limits = (
                                resources.limits
                                if resources and resources.limits
                                else {}
                            )

                            pod_info.append(
                                {
                                    "name": pod.metadata.name,
                                    "node": pod.spec.node_name,
                                    "status": pod.status.phase,
                                    "has_pvc": has_pvc,
                                    "resource_requests": requests,
                                    "resource_limits": limits,
                                    "replicaset": owner.name,
                                }
                            )

                            break  # Found the right owner, no need to check others

            deployment_list.append(
                {
                    "namespace": d.metadata.namespace,
                    "name": d.metadata.name,
                    "replicas": d.status.replicas,
                    "available_replicas": d.status.available_replicas,
                    "ready_replicas": d.status.ready_replicas,
                    "labels": d.metadata.labels,
                    "pods": pod_info,
                }
            )

        return deployment_list

    except client.exceptions.ApiException as e:
        logger.error("Error fetching deployments: %s", e)
        return {"status": "error", "message": str(e)}


def list_all_sts():
    """
    Returns the status of all statefullset in all namespaces.
    """
    try:
        statfull_sts = apps_v1.list_stateful_set_for_all_namespaces(watch=False)
        sts_list = []
        logger.debug(f"{len(statfull_sts.items)} sts found ")
        for s in statfull_sts.items:
            if (
                s.metadata.labels is not None
                and s.metadata.namespace not in protected_namespaces
                and "argocd.argoproj.io/instance" in s.metadata.labels
            ):
                # Get pod information
                pods = core_v1.list_namespaced_pod(
                    s.metadata.namespace,
                    watch=False,
                ).items

                pod_info = []

                for pod in pods:
                    # Method 1: Check owner references
                    if pod.metadata.owner_references:
                        for owner in pod.metadata.owner_references:
                            if (
                                owner.kind == "StatefulSet"
                                and owner.uid == s.metadata.uid
                            ):
                                # Check for PVCs
                                has_pvc = any(
                                    volume.persistent_volume_claim
                                    for volume in pod.spec.volumes
                                    if hasattr(volume, "persistent_volume_claim")
                                )

                                # Get resource requests and limits
                                resources = pod.spec.containers[0].resources
                                requests = (
                                    resources.requests
                                    if resources and resources.requests
                                    else {}
                                )
                                limits = (
                                    resources.limits
                                    if resources and resources.limits
                                    else {}
                                )

                                pod_info.append(
                                    {
                                        "name": pod.metadata.name,
                                        "node": pod.spec.node_name,
                                        "status": pod.status.phase,
                                        "has_pvc": has_pvc,
                                        "resource_requests": requests,
                                        "resource_limits": limits,
                                    }
                                )

                sts_list.append(
                    {
                        "namespace": s.metadata.namespace,
                        "name": s.metadata.name,
                        "replicas": s.status.replicas,
                        "available_replicas": s.status.available_replicas,
                        "ready_replicas": s.status.ready_replicas,
                        "labels": s.metadata.labels,
                        "pods": pod_info,
                    }
                )

        return sts_list
    except client.exceptions.ApiException as e:
        return {"status": "error", "message": str(e)}


@app.get("/live")
def live():
    return {"status": "ok"}


@app.get("/health")
def health():
    """
    Returns the status of all sts in all namespaces.
    """
    try:
        try:
            data = core_v1.list_namespaced_pod(namespace="kube-system")
            pod_list = []
            for pod in data.items:
                pod_list.append(
                    {
                        "name": pod.metadata.name,
                        "status": pod.status.phase,
                        "node": pod.spec.node_name,
                    }
                )
            return {"status": "success", "data": pod_list}
        except client.exceptions.ApiException as e:
            return {"status": "error", "message": str(e)}
        return {"status": "success", "data": data}
    except client.exceptions.ApiException as e:
        return {"status": "error", "message": str(e)}


# Run the application
if __name__ == "__main__":
    import uvicorn

    logger.info("Starting Workload Scheduler...")
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
