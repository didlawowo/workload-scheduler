from fastapi import APIRouter
from kubernetes import client
from loguru import logger
from typing import Any, Dict
from utils.config import protected_namespaces, shutdown_label_selector
from utils.helpers import core_v1, apps_v1
from core.kub_list import list_all_deployments, list_all_sts
from pydantic import BaseModel
from icecream import ic

class PodStatus(BaseModel):
    name: str
    status: str
    node: str

class ReplicaSetResponse(BaseModel):
    status: str
    deleted_replicasets: int = None
    message: str = None

class WorkloadResponse(BaseModel):
    status: str
    message: str

class BulkActionResponse(BaseModel):
    message: str

workload = APIRouter(tags=["Workload Management"])

health_route = APIRouter()

@workload.get(
    "/manage-all/{mode}",
    response_model=BulkActionResponse,
    summary="Manage all deployments and statefulsets",
    description="Scale up or down all deployments and statefulsets in the cluster"
)
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


@workload.get(
    "/shutdown/{resource_type}/{namespace}/{name}",
    response_model=WorkloadResponse,
    summary="Shutdown a specific resource",
    description="Scale down a specific deployment or statefulset to 0 replicas"
)
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
            # application_name = d.metadata.labels["argocd.argoproj.io/instance"]

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
            # application_name = sts.metadata.labels["argocd.argoproj.io/instance"]

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
            # logger.info(f"Disabling auto-sync... for application '{application_name}'")
            # patch_argocd_application(
            #     token=argo_session_token,
            #     app_name=application_name,
            #     enable_auto_sync=False,
            # )
            # logger.success(
            #     f"Auto-sync disabled for application '{application_name}'. Proceeding with scaling down the Deployment."
            # )
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


@workload.get(
    "/up/{uid}",
    response_model=WorkloadResponse,
    summary="Scale up a specific resource",
    description="Scale up a deployment, statefulset, or daemonset"
)
async def scale_up_app(uid: str) -> Dict[str, Any]:
    """
    scale up the specified Deployment, considering protected namespaces and labels.
    """
    logger.info(f"Scaling up {uid}'")

    try:
        c = apps_v1.list_deployment_for_all_namespaces()
        for deploy in c.items :
            if deploy.metadata.uid == uid:
                ic(deploy.metadata.uid)
                logger.success("scaled up deployment")
                return deploy
    except client.exceptions.ApiException as e:
        return {"status": "error", "message": str(e)}

    # elif resource_type == "sts":
    #     try:
    #         c = apps_v1.read_namespaced_stateful_set(name, namespace)
    #         logger.success("scaled up sts")
    #     except client.exceptions.ApiException as e:
    #         return {"status": "error", "message": str(e)}

    # elif resource_type == "ds":
    #     try:
    #         c = apps_v1.read_namespaced_daemon_set(name=name, namespace=namespace)
    #         logger.success("scaled up ds")

        # except client.exceptions.ApiException as e:
        #     return {"status": "error", "message": str(e)}

    # restore auto-sync
    # try:
        # application_name = c.metadata.labels["argocd.argoproj.io/instance"]
        # Step 1: enable auto-sync
        # logger.info(f"Enabling auto-sync for application '{application_name}'")
        # patch_argocd_application(
        #     token=argo_session_token,
        #     app_name=application_name,
        #     enable_auto_sync=True,
        # )
        # logger.success(
        #     f"Auto-sync enabled for application '{application_name}'. Proceeding with scaling down the Deployment."
        # )
        # Define the patch to scale the Deployment
        # body = {"spec": {"replicas": 1}}
        # if resource_type == "deploy":
        #     apps_v1.patch_namespaced_deployment_scale(
        #         name=name, namespace=namespace, body=body
        #     )
        # elif resource_type == "sts":
        #     # Define the patch to scale the Sts

        #     apps_v1.patch_namespaced_stateful_set_scale(
        #         name=name, namespace=namespace, body=body
        #     )
        # elif resource_type == "ds":
        #     logger.info("scaling up ds")
        #     body_ds = {"spec": {"template": {"spec": {"nodeSelector": None}}}}
        #     apps_v1.patch_namespaced_daemon_set(
        #         name=name, namespace=namespace, body=body_ds
        #     )
        #     # logger.debug(res)
        # return {
        #     "status": "success",
        #     "message": f"{resource_type} '{name}' in namespace '{namespace}' has been scaled up",
        # }
    # except client.exceptions.ApiException as e:
    #     logger.error(e)
    #     return {"status": "error", "message": str(e)}


@workload.get(
    "/delete-rs",
    response_model=ReplicaSetResponse,
    summary="Delete ReplicaSets with zero replicas",
    description="Deletes all ReplicaSets with desired replicas set to 0"
)
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


@health_route.get(
    "/live",
    response_model=WorkloadResponse,
    summary="Application liveness check",
    description="Check if the application is live"
)
def live():
    # logger.info("Checking if the application is live...")
    return {"status": "success", "message": "Application is live"}


@health_route.get(
    "/health",
    summary="Kubernetes health check",
    description="Returns the status of all sts in all namespaces."
)
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
