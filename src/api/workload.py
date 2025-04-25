from fastapi import APIRouter
from kubernetes import client
from loguru import logger
from typing import Any, Dict
from utils.config import protected_namespaces
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

                await manage_status("down", "deploy", deploy['uid'])
            elif mode == "up":
                logger.info(
                    f"Scaling up deploy '{deploy['name']}' in namespace '{deploy['namespace']}'"
                )
                await manage_status("up", "deploy", deploy['uid'])

        for sts in sts_list:
            if mode == "down":
                logger.info(
                    f"Scaling down StatefulSet '{sts['name']}' in namespace '{sts['namespace']}'"
                )

                await manage_status("down", "sts", deploy['uid'])
            elif mode == "up":
                logger.info(
                    f"Scaling up StatefulSet '{sts['name']}' in namespace '{sts['namespace']}'"
                )
                await manage_status("up", "sts", deploy['uid'])
        # For simplicity, this example responds with a success message regardless of individual failures
        return {
            "message": "Bulk action to scale down deployments initiated. Check logs for individual action results."
        }
    except Exception as e:
        logger.error(f"Error while scaling down all workload Error: {e}")

@workload.get(
    "/manage/{action}/{resource_type}/{uid}",
    response_model=WorkloadResponse,
    summary="Manage status a specific resource",
    description="Manage deployment, statefulset, or daemonset status"
)
async def manage_status(action: str, resource_type: str, uid: str) -> Dict[str, Any]:
    """
    scale up or shutdown the specified Deployment, considering protected namespaces and labels.
    """
    logger.info(f"Manage {uid}'")

    try:
        action_nbr = 0
        if resource_type == "deploy":
            c = apps_v1.list_deployment_for_all_namespaces()
            if action == "up":
                action_nbr = 1
            for deploy in c.items :
                if deploy.metadata.uid == uid:
                    ic(deploy.metadata.uid)
                    body = {"spec": {"replicas": action_nbr}}
                    apps_v1.patch_namespaced_deployment_scale(
                        name=deploy.metadata.name, namespace=deploy.metadata.namespace, body=body
                    )
                    logger.success(f"Scaled {[action]} deplyment")
                    return {
            "status": "success",
            "message": f"deployment '{deploy.metadata.name}' in namespace '{deploy.metadata.namespace}' has been scaled '{action}'",
        }
        
        elif resource_type == "sts":
            c = apps_v1.list_stateful_set_for_all_namespaces()
            if action == "up":
                action_nbr = 1
            for stateful_set in c.items :
                if stateful_set.metadata.uid == uid:
                    ic(stateful_set.metadata.uid)
                    body = {"spec": {"replicas": action_nbr}}
                    apps_v1.patch_namespaced_stateful_set_scale(
                        name=stateful_set.metadata.name, namespace=stateful_set.metadata.namespace, body=body
                    )
                    logger.success(f"Scaled {[action]} sts")
                    return {
            "status": "success",
            "message": f"deployment '{stateful_set.metadata.name}' in namespace '{stateful_set.metadata.namespace}' has been scaled '{action}'",
        }

        elif resource_type == "ds":
            c = apps_v1.list_daemon_set_for_all_namespaces()
            if action == "up":
                action_nbr = 1
            for daemonset in c.items :
                if daemonset.metadata.uid == uid:
                    ic(daemonset.metadata.uid)
                    body = {"spec": {"replicas": action_nbr}}
                    apps_v1.patch_namespaced_daemon_set(
                        name=daemonset.metadata.name, namespace=daemonset.metadata.namespace, body=body
                    )
                    logger.success(f"Scaled {[action]} daemonset")
            
                    return {
            "status": "success",
            "message": f"deployment '{daemonset.metadata.name}' in namespace '{daemonset.metadata.namespace}' has been scaled '{action}'",
        }
        else:
            logger.error(f"Unknown resource type: {resource_type}")
            return {"status": "error", "message": f"Unknown resource type: {resource_type}"}
     
        # TODO restore auto-sync
  
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
      
   

    except client.exceptions.ApiException as e:
        logger.error(e)
        return {"status": "error", "message": str(e)}


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
