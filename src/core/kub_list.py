from kubernetes import client
from loguru import logger


def list_all_daemonsets(apps_v1, core_v1, protected_namespaces):
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
                            # node_conditions = {}
                            # if pod.spec.node_name:
                            #     try:
                            #         node = core_v1.read_node(pod.spec.node_name)
                            #         node_conditions = {
                            #             cond.type: cond.status
                            #             for cond in node.status.conditions
                            #         }
                            #     except client.exceptions.ApiException:
                            #         logger.warning(
                            #             f"Could not fetch conditions for node {pod.spec.node_name}"
                            #         )

                            pod_info.append(
                                {
                                    "name": pod.metadata.name,
                                    "node": pod.spec.node_name,
                                    "status": pod.status.phase,
                                    "has_pvc": has_pvc,
                                    "resource_requests": requests,
                                    "resource_limits": limits,
                                    "node_conditions": "",  # node_conditions,
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


def list_all_deployments(apps_v1, core_v1, protected_namespaces):
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
                # or d.metadata.labels is None
                or d.metadata.namespace in protected_namespaces
                # or "argocd.argoproj.io/instance" not in d.metadata.labels
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
                            # has_pvc = any(
                            #     volume.persistent_volume_claim
                            #     for volume in pod.spec.volumes
                            #     if hasattr(volume, "persistent_volume_claim")
                            # )

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
                                    "has_pvc": False,
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


def list_all_sts(apps_v1, core_v1, protected_namespaces):
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

