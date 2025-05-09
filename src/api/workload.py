from fastapi import APIRouter
from kubernetes import client
from loguru import logger
from typing import Any, Dict
from utils.argocd import handle_argocd_auto_sync
from utils.config import protected_namespaces
from utils.helpers import core_v1, apps_v1
from core.dbManager import DatabaseManager
from pydantic import BaseModel
from icecream import ic
import os

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

async def process_deployment(deploy, mode):
    """Traite un déploiement pour le scaling up/down"""
    try:
        deploy_name = deploy.metadata.name
        deploy_namespace = deploy.metadata.namespace
        deploy_uid = deploy.metadata.uid
        
        if deploy_namespace in protected_namespaces:
            logger.info(f"Skipping deployment {deploy_name} in protected namespace {deploy_namespace}")
            return
        
        if mode == "down":
            logger.info(f"Scaling down deployment '{deploy_name}' in namespace '{deploy_namespace}'")
            await manage_status("down", "deploy", deploy_uid)
        elif mode == "up":
            logger.info(f"Scaling up deployment '{deploy_name}' in namespace '{deploy_namespace}'")
            await manage_status("up", "deploy", deploy_uid)
    except Exception as e:
        logger.error(f"Error processing deployment {deploy.metadata.name}: {e}")

async def process_statefulset(sts, mode):
    """Traite un statefulset pour le scaling up/down"""
    try:
        sts_name = sts.metadata.name
        sts_namespace = sts.metadata.namespace
        sts_uid = sts.metadata.uid
        
        if sts_namespace in protected_namespaces:
            logger.info(f"Skipping statefulset {sts_name} in protected namespace {sts_namespace}")
            return
        
        if mode == "down":
            logger.info(f"Scaling down StatefulSet '{sts_name}' in namespace '{sts_namespace}'")
            await manage_status("down", "sts", sts_uid)
        elif mode == "up":
            logger.info(f"Scaling up StatefulSet '{sts_name}' in namespace '{sts_namespace}'")
            await manage_status("up", "sts", sts_uid)
    except Exception as e:
        logger.error(f"Error processing statefulset {sts.metadata.name}: {e}")

@workload.get(
    "/manage-all/{mode}",
    response_model=BulkActionResponse,
    summary="Manage all deployments and statefulsets",
    description="Scale up or down all deployments and statefulsets in the cluster"
)
async def manage_all_deployments(mode: str) -> Dict[str, Any]:
    """Gère tous les déploiements et statefulsets dans le cluster"""
    logger.info("Received request to manage all workloads.")
    logger.info(f"mode: {mode}")
    try:
        deployments = apps_v1.list_deployment_for_all_namespaces()
        logger.info(f"Found {len(deployments.items)} deployments to process")
        
        statefulsets = apps_v1.list_stateful_set_for_all_namespaces()
        logger.info(f"Found {len(statefulsets.items)} statefulsets to process")
        
        for deploy in deployments.items:
            await process_deployment(deploy, mode)
        
        for sts in statefulsets.items:
            await process_statefulset(sts, mode)
                
        return {
            "message": f"Bulk action to {mode} all workloads initiated. Check logs for individual action results."
        }
    except Exception as e:
        logger.error(f"Error while scaling {mode} all workloads: {e}")
        return {
            "message": f"Error while scaling {mode} all workloads: {str(e)}"
        }

async def scale_deployment(uid, action_nbr):
    """Scale un déploiement spécifique"""
    c = apps_v1.list_deployment_for_all_namespaces()
    for deploy in c.items:
        if deploy.metadata.uid == uid:
            ic(deploy.metadata.uid)
            body = {"spec": {"replicas": action_nbr}}
            apps_v1.patch_namespaced_deployment_scale(
                name=deploy.metadata.name, namespace=deploy.metadata.namespace, body=body
            )
            logger.success(f"Scaled deployment to {action_nbr} replicas")
            return {
                "status": "success",
                "message": f"deployment '{deploy.metadata.name}' in namespace '{deploy.metadata.namespace}' has been scaled accordingly",
            }
    return None

async def scale_statefulset(uid, action_nbr):
    """Scale un statefulset spécifique"""
    c = apps_v1.list_stateful_set_for_all_namespaces()
    for stateful_set in c.items:
        if stateful_set.metadata.uid == uid:
            ic(stateful_set.metadata.uid)
            body = {"spec": {"replicas": action_nbr}}
            apps_v1.patch_namespaced_stateful_set_scale(
                name=stateful_set.metadata.name, namespace=stateful_set.metadata.namespace, body=body
            )
            logger.success(f"Scaled statefulset to {action_nbr} replicas")
            return {
                "status": "success",
                "message": f"statefulset '{stateful_set.metadata.name}' in namespace '{stateful_set.metadata.namespace}' has been scaled accordingly",
            }
    return None

async def scale_daemonset(uid, action_nbr):
    """Scale un daemonset spécifique"""
    c = apps_v1.list_daemon_set_for_all_namespaces()
    for daemonset in c.items:
        if daemonset.metadata.uid == uid:
            ic(daemonset.metadata.uid)
            body = {"spec": {"replicas": action_nbr}}
            apps_v1.patch_namespaced_daemon_set(
                name=daemonset.metadata.name, namespace=daemonset.metadata.namespace, body=body
            )
            logger.success(f"Scaled daemonset to {action_nbr} replicas")
            return {
                "status": "success",
                "message": f"daemonset '{daemonset.metadata.name}' in namespace '{daemonset.metadata.namespace}' has been scaled accordingly",
            }
    return None

@workload.get(
    "/manage/{action}/{resource_type}/{uid}",
    response_model=WorkloadResponse,
    summary="Manage status a specific resource",
    description="Manage deployment, statefulset, or daemonset status"
)
async def manage_status(action: str, resource_type: str, uid: str) -> Dict[str, Any]:
    """Scale up or shutdown the specified resource"""
    logger.info(f"Managing resource {uid} of type {resource_type} with action {action}")

    try:
        action_nbr = 1 if action == "up" else 0
        result = None
        
        if resource_type == "deploy":
            result = await scale_deployment(uid, action_nbr)
        elif resource_type == "sts":
            result = await scale_statefulset(uid, action_nbr)
        elif resource_type == "ds":
            result = await scale_daemonset(uid, action_nbr)
        else:
            logger.error(f"Unknown resource type: {resource_type}")
            return {"status": "error", "message": f"Unknown resource type: {resource_type}"}
            
        if result:
            return result
        
        return {"status": "error", "message": f"Resource with UID {uid} not found"}
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
    """Deletes all ReplicaSets with desired replicas set to 0."""
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
    """Simple liveness check"""
    return {"status": "success", "message": "Application is live"}

async def check_database():
    """Vérifie l'état de la base de données"""
    db_result = {"status": "success"}
    db_manager = DatabaseManager()
    try:
        tables_exist = await db_manager.check_table_exists()
        db_result["details"] = "Tables présentes" if tables_exist else "Base accessible mais tables non trouvées"
    except Exception as e:
        db_result["status"] = "error"
        db_result["message"] = str(e)
    finally:
        await db_manager.close()
    return db_result

async def check_kubernetes():
    """Vérifie l'état du cluster Kubernetes"""
    k8s_result = {"status": "success"}
    try:
        data = core_v1.list_namespaced_pod(namespace="kube-system")
        pod_list = []
        for pod in data.items:
            pod_list.append({
                "name": pod.metadata.name,
                "status": pod.status.phase,
                "node": pod.spec.node_name,
            })
        k8s_result["details"] = pod_list
    except client.exceptions.ApiException as e:
        k8s_result["status"] = "error"
        k8s_result["message"] = str(e)
    return k8s_result

@health_route.get(
    "/health",
    summary="Kubernetes health check",
    description="Returns the status of all sts in all namespaces."
)
async def health():
    """Vérifie l'état général de l'application"""
    health_status = {
        "status": "success",
        "database": await check_database(),
        "kubernetes": await check_kubernetes()
    }
    
    if health_status["database"]["status"] == "error" or health_status["kubernetes"]["status"] == "error":
        health_status["status"] = "error"
        
    return health_status