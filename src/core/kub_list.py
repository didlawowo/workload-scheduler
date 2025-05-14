from kubernetes import client
from loguru import logger
from icecream import ic

def get_pod_details(pod, owner_type="DaemonSet", owner_name=None, owner_uid=None):
    """
    Extrait les détails d'un pod pour un propriétaire spécifique.
    """
    # Check for PVCs
    has_pvc = any(
        volume.persistent_volume_claim
        for volume in pod.spec.volumes or []
        if hasattr(volume, "persistent_volume_claim") and volume.persistent_volume_claim
    )

    # Get resource requests and limits
    resources = pod.spec.containers[0].resources if pod.spec.containers else None
    requests = resources.requests if resources and resources.requests else {}
    limits = resources.limits if resources and resources.limits else {}

    pod_info = {
        "name": pod.metadata.name,
        "node": pod.spec.node_name,
        "status": pod.status.phase,
        "has_pvc": has_pvc,
        "resource_requests": requests,
        "resource_limits": limits,
    }
    
    if owner_type == "DaemonSet":
        pod_info["start_time"] = pod.status.start_time.isoformat() if pod.status.start_time else None
        pod_info["node_conditions"] = ""
    elif owner_type == "Deployment":
        pod_info["uid"] = pod.metadata.uid
        pod_info["replicaset"] = owner_name
        
    return pod_info

def filter_pods_by_owner(pods, owner_type, owner_name=None, owner_uid=None):
    """
    Filtre les pods par type de propriétaire et nom/uid.
    """
    pod_info = []
    for pod in pods:
        if not pod.metadata.owner_references:
            continue
            
        for owner in pod.metadata.owner_references:
            match_found = False
            if owner_type == "DaemonSet" and owner.kind == "DaemonSet" and owner.name == owner_name:
                match_found = True
            elif owner_type == "StatefulSet" and owner.kind == "StatefulSet" and owner.uid == owner_uid:
                match_found = True
            elif owner_type == "ReplicaSet" and owner.kind == "ReplicaSet" and owner.name == owner_name:
                match_found = True
                
            if match_found:
                pod_details = get_pod_details(pod, owner_type, owner_name, owner_uid)
                pod_info.append(pod_details)
                break
                
    return pod_info

def find_active_replicasets(replicasets, deployment_name):
    """
    Trouve les ReplicaSets actifs pour un déploiement spécifique.
    """
    active_rs = []
    for rs in replicasets.items:
        if rs.metadata.owner_references:
            for owner in rs.metadata.owner_references:
                if owner.kind == "Deployment" and owner.name == deployment_name:
                    active_rs.append(rs)
                    break
    
    active_rs.sort(key=lambda x: x.metadata.creation_timestamp, reverse=True)
    return active_rs

def list_all_daemonsets(apps_v1, core_v1, protected_namespaces, protected_labels):
    """
    Returns the status of all DaemonSets in all namespaces, including pod information.
    """
    try:
        logger.info("Fetching all DaemonSets across namespaces")
        daemonsets = apps_v1.list_daemon_set_for_all_namespaces(watch=False)
        logger.debug(f"{len(daemonsets.items)} DaemonSets found in total")
        daemonset_list = []

        for ds in daemonsets.items:
            should_skip = ds.metadata.labels is None or ds.metadata.namespace in protected_namespaces
            
            if not should_skip and ds.metadata.labels:
                for key, value in protected_labels.items():
                    if key in ds.metadata.labels and ds.metadata.labels[key] == value:
                        should_skip = True
                        break
            
            if should_skip:
                logger.debug(f"Skipping DaemonSet {ds.metadata.name} in namespace {ds.metadata.namespace}")
                continue

            logger.debug(f"Processing DaemonSet {ds.metadata.name} in namespace {ds.metadata.namespace}")
            pods = core_v1.list_namespaced_pod(ds.metadata.namespace).items
            pod_info = filter_pods_by_owner(pods, "DaemonSet", owner_name=ds.metadata.name)
            
            # Get DaemonSet-specific status
            status = get_daemonset_status(ds)
            
            logger.debug(f"DaemonSet {ds.metadata.name} status: {ds.status.number_ready}/{ds.status.desired_number_scheduled} pods ready")
            daemonset_info = create_daemonset_info(ds, status, pod_info)
            daemonset_list.append(daemonset_info)

        logger.info(f"Processed {len(daemonset_list)} DaemonSets after filtering")
        return daemonset_list

    except client.exceptions.ApiException as e:
        logger.error(f"Error fetching DaemonSets: {str(e)}")
        return {"status": "error", "message": str(e)}

def get_daemonset_status(ds):
    """Extrait les informations de statut d'un DaemonSet."""
    return {
        "desired_number_scheduled": ds.status.desired_number_scheduled,
        "current_number_scheduled": ds.status.current_number_scheduled,
        "number_ready": ds.status.number_ready,
        "updated_number_scheduled": ds.status.updated_number_scheduled,
        "number_available": ds.status.number_available if hasattr(ds.status, "number_available") else None,
        "number_misscheduled": ds.status.number_misscheduled,
    }

def create_daemonset_info(ds, status, pod_info):
    """Crée un dictionnaire d'information pour un DaemonSet."""
    return {
        "namespace": ds.metadata.namespace,
        "name": ds.metadata.name,
        "uid": ds.metadata.uid,
        "labels": ds.metadata.labels,
        "status": status,
        "pods": pod_info,
        "update_strategy": ds.spec.update_strategy.type if ds.spec.update_strategy else None,
        "selector": ds.spec.selector.match_labels,
    }

def list_all_deployments(apps_v1, core_v1, protected_namespaces, protected_labels):
    """
    Returns the status of all Deployments in all namespaces, including pod information.
    """
    try:
        logger.info("Fetching all Deployments across namespaces")
        deployments = apps_v1.list_deployment_for_all_namespaces(watch=False)
        logger.debug(f"{len(deployments.items)} deployments found")
        deployment_list = []
        for d in deployments.items:
            # Skip if not matching our criteria
            ic(d.metadata.labels)
            
            should_skip = False
            if d.metadata.name == "workload-scheduler" or d.metadata.namespace in protected_namespaces:
                should_skip = True
            elif d.metadata.labels:
                for key, value in protected_labels.items():
                    if key in d.metadata.labels and d.metadata.labels[key] == value:
                        should_skip = True
                        break
            
            if should_skip:
                logger.debug(f"Skipping Deployment {d.metadata.name} in namespace {d.metadata.namespace}")
                continue
                
            logger.debug(f"Processing Deployment {d.metadata.name} in namespace {d.metadata.namespace}")
            deployment_info = process_deployment(d, apps_v1, core_v1)
            deployment_list.append(deployment_info)
        
        logger.info(f"Processed {len(deployment_list)} Deployments after filtering")
        return deployment_list
    except client.exceptions.ApiException as e:
        logger.error("Error fetching deployments: %s", e)
        return {"status": "error", "message": str(e)}

def process_deployment(deployment, apps_v1, core_v1):
    """
    Traite un déploiement pour extraire ses informations et celles de ses pods.
    """
    replicasets = apps_v1.list_namespaced_replica_set(
        deployment.metadata.namespace,
        label_selector=",".join([f"{k}={v}" for k, v in deployment.spec.selector.match_labels.items()])
    )
    logger.debug(f"Found {len(replicasets.items)} ReplicaSets for Deployment {deployment.metadata.name}")
    
    active_rs = find_active_replicasets(replicasets, deployment.metadata.name)
    
    pods = core_v1.list_namespaced_pod(deployment.metadata.namespace, watch=False).items
    
    pod_info = []
    for rs in active_rs:
        rs_pods = filter_pods_by_owner(pods, "ReplicaSet", owner_name=rs.metadata.name)
        pod_info.extend(rs_pods)
    
    logger.debug(f"Deployment {deployment.metadata.name} has {len(pod_info)} pods")
    
    return {
        "namespace": deployment.metadata.namespace,
        "name": deployment.metadata.name,
        "uid": deployment.metadata.uid,
        "replicas": deployment.status.replicas,
        "available_replicas": deployment.status.available_replicas,
        "ready_replicas": deployment.status.ready_replicas,
        "labels": deployment.metadata.labels,
        "pods": pod_info,
    }

def list_all_sts(apps_v1, core_v1, protected_namespaces, protected_labels):
    """
    Returns the status of all StatefulSets in all namespaces.
    """
    try:
        logger.info("Fetching all StatefulSets across namespaces")
        statfull_sts = apps_v1.list_stateful_set_for_all_namespaces(watch=False)
        logger.debug(f"{len(statfull_sts.items)} StatefulSets found")
        sts_list = []

        for s in statfull_sts.items:
            if not meets_sts_criteria(s, protected_namespaces, protected_labels):
                logger.debug(f"Skipping StatefulSet {s.metadata.name} in namespace {s.metadata.namespace}")
                continue
                
            logger.debug(f"Processing StatefulSet {s.metadata.name} in namespace {s.metadata.namespace}")
            sts_info = process_statefulset(s, core_v1)
            sts_list.append(sts_info)

        logger.info(f"Processed {len(sts_list)} StatefulSets after filtering")
        return sts_list
        
    except client.exceptions.ApiException as e:
        logger.error(f"Error fetching StatefulSets: {str(e)}")
        return {"status": "error", "message": str(e)}

def meets_sts_criteria(statefulset, protected_namespaces, protected_labels):
    """
    Vérifie si un StatefulSet répond aux critères de sélection.
    """
    if statefulset.metadata.labels is None or statefulset.metadata.namespace in protected_namespaces:
        return False
        
    if "argocd.argoproj.io/instance" not in statefulset.metadata.labels:
        return False
        
    for key, value in protected_labels.items():
        if key in statefulset.metadata.labels and statefulset.metadata.labels[key] == value:
            return False
            
    return True

def process_statefulset(statefulset, core_v1):
    """
    Traite un StatefulSet pour extraire ses informations et celles de ses pods.
    """
    pods = core_v1.list_namespaced_pod(statefulset.metadata.namespace, watch=False).items
    pod_info = filter_pods_by_owner(pods, "StatefulSet", owner_uid=statefulset.metadata.uid)
    
    logger.debug(f"StatefulSet {statefulset.metadata.name} has {len(pod_info)} pods")
    
    return {
        "namespace": statefulset.metadata.namespace,
        "name": statefulset.metadata.name,
        "uid": statefulset.metadata.uid,
        "replicas": statefulset.status.replicas,
        "available_replicas": statefulset.status.available_replicas,
        "ready_replicas": statefulset.status.ready_replicas,
        "labels": statefulset.metadata.labels,
        "pods": pod_info,
    }