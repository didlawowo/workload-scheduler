import pytest
from unittest.mock import MagicMock, patch
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.kub_list import (
    get_pod_details,
    filter_pods_by_owner,
    find_active_replicasets,
    list_all_daemonsets,
    get_daemonset_status,
    create_daemonset_info,
    list_all_deployments,
    process_deployment,
    list_all_sts,
    meets_sts_criteria,
    process_statefulset
)


@pytest.fixture
def mock_pod():
    """Crée un mock de pod Kubernetes"""
    pod = MagicMock()
    
    pod.metadata.name = "test-pod"
    pod.metadata.uid = "test-pod-uid"
    pod.metadata.owner_references = [MagicMock()]
    pod.spec.node_name = "test-node"
    pod.spec.volumes = [MagicMock()]
    pod.spec.volumes[0].persistent_volume_claim = None
    pod.spec.containers = [MagicMock()]
    pod.spec.containers[0].resources = MagicMock()
    pod.spec.containers[0].resources.requests = {"cpu": "100m", "memory": "128Mi"}
    pod.spec.containers[0].resources.limits = {"cpu": "200m", "memory": "256Mi"}
    pod.status.phase = "Running"
    pod.status.start_time = MagicMock()
    pod.status.start_time.isoformat.return_value = "2025-05-07T12:00:00Z"
    
    return pod


@pytest.fixture
def mock_daemonset():
    """Crée un mock de DaemonSet Kubernetes"""
    ds = MagicMock()
    
    ds.metadata.name = "test-daemonset"
    ds.metadata.namespace = "test-namespace"
    ds.metadata.uid = "test-ds-uid"
    ds.metadata.labels = {"app": "test-app"}
    ds.spec.selector.match_labels = {"app": "test-app"}
    ds.spec.update_strategy.type = "RollingUpdate"
    ds.status.desired_number_scheduled = 3
    ds.status.current_number_scheduled = 3
    ds.status.number_ready = 3
    ds.status.updated_number_scheduled = 3
    ds.status.number_available = 3
    ds.status.number_misscheduled = 0
    
    return ds


@pytest.fixture
def mock_deployment():
    """Crée un mock de Deployment Kubernetes"""
    deployment = MagicMock()
    
    deployment.metadata.name = "test-deployment"
    deployment.metadata.namespace = "test-namespace"
    deployment.metadata.uid = "test-deploy-uid"
    deployment.metadata.labels = {"app": "test-app"}
    deployment.spec.selector.match_labels = {"app": "test-app"}
    deployment.status.replicas = 3
    deployment.status.available_replicas = 3
    deployment.status.ready_replicas = 3
    
    return deployment


@pytest.fixture
def mock_statefulset():
    """Crée un mock de StatefulSet Kubernetes"""
    sts = MagicMock()
    
    sts.metadata.name = "test-statefulset"
    sts.metadata.namespace = "test-namespace"
    sts.metadata.uid = "test-sts-uid"
    sts.metadata.labels = {
        "app": "test-app",
        "argocd.argoproj.io/instance": "test-instance"
    }
    sts.status.replicas = 3
    sts.status.available_replicas = 3
    sts.status.ready_replicas = 3
    
    return sts


@pytest.fixture
def mock_k8s_client():
    """Mock pour le client Kubernetes"""
    with patch('kubernetes.client') as mock_client:
        yield mock_client


def test_get_pod_details_daemonset(mock_pod):
    """Test de get_pod_details pour un DaemonSet"""
    result = get_pod_details(mock_pod, owner_type="DaemonSet", owner_name="test-daemonset")
    
    assert result["name"] == "test-pod"
    assert result["node"] == "test-node"
    assert result["status"] == "Running"
    assert result["has_pvc"] is False
    assert result["resource_requests"] == {"cpu": "100m", "memory": "128Mi"}
    assert result["resource_limits"] == {"cpu": "200m", "memory": "256Mi"}
    assert result["start_time"] == "2025-05-07T12:00:00Z"
    assert result["node_conditions"] == ""


def test_get_pod_details_deployment(mock_pod):
    """Test de get_pod_details pour un Deployment"""
    result = get_pod_details(mock_pod, owner_type="Deployment", owner_name="test-replicaset")
    
    assert result["name"] == "test-pod"
    assert result["node"] == "test-node"
    assert result["status"] == "Running"
    assert result["has_pvc"] is False
    assert result["uid"] == "test-pod-uid"
    assert result["replicaset"] == "test-replicaset"


def test_get_pod_details_with_pvc(mock_pod):
    """Test de get_pod_details avec un PVC"""
    mock_pod.spec.volumes[0].persistent_volume_claim = MagicMock()
    
    result = get_pod_details(mock_pod)
    
    assert result["has_pvc"] is True


def test_filter_pods_by_owner_daemonset(mock_pod):
    """Test de filter_pods_by_owner pour un DaemonSet"""
    mock_pod.metadata.owner_references[0].kind = "DaemonSet"
    mock_pod.metadata.owner_references[0].name = "test-daemonset"
    
    result = filter_pods_by_owner([mock_pod], "DaemonSet", owner_name="test-daemonset")
    
    assert len(result) == 1
    assert result[0]["name"] == "test-pod"


def test_filter_pods_by_owner_statefulset(mock_pod):
    """Test de filter_pods_by_owner pour un StatefulSet"""
    mock_pod.metadata.owner_references[0].kind = "StatefulSet"
    mock_pod.metadata.owner_references[0].uid = "test-sts-uid"
    
    result = filter_pods_by_owner([mock_pod], "StatefulSet", owner_uid="test-sts-uid")
    
    assert len(result) == 1
    assert result[0]["name"] == "test-pod"


def test_filter_pods_by_owner_replicaset(mock_pod):
    """Test de filter_pods_by_owner pour un ReplicaSet"""
    mock_pod.metadata.owner_references[0].kind = "ReplicaSet"
    mock_pod.metadata.owner_references[0].name = "test-replicaset"
    
    result = filter_pods_by_owner([mock_pod], "ReplicaSet", owner_name="test-replicaset")
    
    assert len(result) == 1
    assert result[0]["name"] == "test-pod"


def test_filter_pods_by_owner_no_match(mock_pod):
    """Test de filter_pods_by_owner sans correspondance"""
    mock_pod.metadata.owner_references[0].kind = "DaemonSet"
    mock_pod.metadata.owner_references[0].name = "other-daemonset"
    
    result = filter_pods_by_owner([mock_pod], "DaemonSet", owner_name="test-daemonset")
    
    assert len(result) == 0


def test_find_active_replicasets():
    """Test de find_active_replicasets"""
    replicaset1 = MagicMock()
    replicaset1.metadata.owner_references = [MagicMock()]
    replicaset1.metadata.owner_references[0].kind = "Deployment"
    replicaset1.metadata.owner_references[0].name = "test-deployment"
    replicaset1.metadata.creation_timestamp = "2025-05-01T12:00:00Z"
    
    replicaset2 = MagicMock()
    replicaset2.metadata.owner_references = [MagicMock()]
    replicaset2.metadata.owner_references[0].kind = "Deployment"
    replicaset2.metadata.owner_references[0].name = "test-deployment"
    replicaset2.metadata.creation_timestamp = "2025-05-07T12:00:00Z"
    
    replicaset3 = MagicMock()
    replicaset3.metadata.owner_references = [MagicMock()]
    replicaset3.metadata.owner_references[0].kind = "Deployment"
    replicaset3.metadata.owner_references[0].name = "other-deployment"
    
    replicasets = MagicMock()
    replicasets.items = [replicaset1, replicaset2, replicaset3]
    
    result = find_active_replicasets(replicasets, "test-deployment")
    
    assert len(result) == 2
    assert result[0] == replicaset2


def test_get_daemonset_status(mock_daemonset):
    """Test de get_daemonset_status"""
    result = get_daemonset_status(mock_daemonset)
    
    assert result["desired_number_scheduled"] == 3
    assert result["current_number_scheduled"] == 3
    assert result["number_ready"] == 3
    assert result["updated_number_scheduled"] == 3
    assert result["number_available"] == 3
    assert result["number_misscheduled"] == 0


def test_create_daemonset_info(mock_daemonset):
    """Test de create_daemonset_info"""
    pod_info = [{"name": "test-pod", "node": "test-node"}]
    
    status = {
        "desired_number_scheduled": 3,
        "current_number_scheduled": 3,
        "number_ready": 3,
        "updated_number_scheduled": 3,
        "number_available": 3,
        "number_misscheduled": 0,
    }
    
    result = create_daemonset_info(mock_daemonset, status, pod_info)
    
    assert result["namespace"] == "test-namespace"
    assert result["name"] == "test-daemonset"
    assert result["uid"] == "test-ds-uid"
    assert result["labels"] == {"app": "test-app"}
    assert result["status"] == status
    assert result["pods"] == pod_info
    assert result["update_strategy"] == "RollingUpdate"
    assert result["selector"] == {"app": "test-app"}


def test_list_all_daemonsets():
    """Test de list_all_daemonsets"""
    apps_v1 = MagicMock()
    core_v1 = MagicMock()
    
    daemonset = MagicMock()
    daemonset.metadata.name = "test-daemonset"
    daemonset.metadata.namespace = "test-namespace"
    daemonset.metadata.labels = {"app": "test-app"}
    
    daemonsets = MagicMock()
    daemonsets.items = [daemonset]
    
    apps_v1.list_daemon_set_for_all_namespaces.return_value = daemonsets
    
    pod = MagicMock()
    pod.metadata.name = "test-pod"
    pod.metadata.owner_references = [MagicMock()]
    pod.metadata.owner_references[0].kind = "DaemonSet"
    pod.metadata.owner_references[0].name = "test-daemonset"
    
    pods = MagicMock()
    pods.items = [pod]
    
    core_v1.list_namespaced_pod.return_value = pods
    
    result = list_all_daemonsets(apps_v1, core_v1, ["kube-system"])
    
    assert len(result) == 1
    assert result[0]["name"] == "test-daemonset"
    assert result[0]["namespace"] == "test-namespace"
    
    apps_v1.list_daemon_set_for_all_namespaces.assert_called_once()
    core_v1.list_namespaced_pod.assert_called_once_with("test-namespace")


def test_list_all_daemonsets_skip_protected():
    """Test de list_all_daemonsets avec un namespace protégé"""
    apps_v1 = MagicMock()
    core_v1 = MagicMock()
    
    daemonset = MagicMock()
    daemonset.metadata.name = "test-daemonset"
    daemonset.metadata.namespace = "kube-system"
    daemonset.metadata.labels = {"app": "test-app"}
    
    daemonsets = MagicMock()
    daemonsets.items = [daemonset]
    
    apps_v1.list_daemon_set_for_all_namespaces.return_value = daemonsets
    
    result = list_all_daemonsets(apps_v1, core_v1, ["kube-system"])
    
    assert len(result) == 0
    
    apps_v1.list_daemon_set_for_all_namespaces.assert_called_once()
    core_v1.list_namespaced_pod.assert_not_called()


def test_list_all_daemonsets_api_exception():
    """Test de list_all_daemonsets avec une exception de l'API"""
    apps_v1 = MagicMock()
    core_v1 = MagicMock()
    
    from kubernetes.client.exceptions import ApiException
    apps_v1.list_daemon_set_for_all_namespaces.side_effect = ApiException("API Error")
    
    result = list_all_daemonsets(apps_v1, core_v1, ["kube-system"])
    
    assert "status" in result
    assert result["status"] == "error"
    assert "message" in result
    assert "API Error" in result["message"]


def test_process_deployment(mock_deployment):
    """Test de process_deployment"""
    apps_v1 = MagicMock()
    core_v1 = MagicMock()
    
    replicaset = MagicMock()
    replicaset.metadata.name = "test-replicaset"
    replicaset.metadata.owner_references = [MagicMock()]
    replicaset.metadata.owner_references[0].kind = "Deployment"
    replicaset.metadata.owner_references[0].name = "test-deployment"
    replicaset.metadata.creation_timestamp = "2025-05-07T12:00:00Z"
    
    replicasets = MagicMock()
    replicasets.items = [replicaset]
    
    apps_v1.list_namespaced_replica_set.return_value = replicasets
    
    pod = MagicMock()
    pod.metadata.name = "test-pod"
    pod.metadata.owner_references = [MagicMock()]
    pod.metadata.owner_references[0].kind = "ReplicaSet"
    pod.metadata.owner_references[0].name = "test-replicaset"
    
    pods = MagicMock()
    pods.items = [pod]
    
    core_v1.list_namespaced_pod.return_value = pods
    
    result = process_deployment(mock_deployment, apps_v1, core_v1)
    
    assert result["namespace"] == "test-namespace"
    assert result["name"] == "test-deployment"
    assert result["uid"] == "test-deploy-uid"
    assert result["replicas"] == 3
    assert result["available_replicas"] == 3
    assert result["ready_replicas"] == 3
    assert result["labels"] == {"app": "test-app"}
    assert len(result["pods"]) == 1
    assert result["pods"][0]["name"] == "test-pod"
    
    apps_v1.list_namespaced_replica_set.assert_called_once()
    core_v1.list_namespaced_pod.assert_called_once_with("test-namespace", watch=False)


def test_list_all_deployments():
    """Test de list_all_deployments"""
    apps_v1 = MagicMock()
    core_v1 = MagicMock()
    
    deployment = MagicMock()
    deployment.metadata.name = "test-deployment"
    deployment.metadata.namespace = "test-namespace"
    deployment.spec.selector.match_labels = {"app": "test-app"}
    
    deployments = MagicMock()
    deployments.items = [deployment]
    
    apps_v1.list_deployment_for_all_namespaces.return_value = deployments
    
    # Here's the important change, using the correct module path:
    with patch('core.kub_list.process_deployment') as mock_process:
        mock_process.return_value = {
            "namespace": "test-namespace",
            "name": "test-deployment",
            "uid": "test-deploy-uid",
            "replicas": 3,
            "available_replicas": 3,
            "ready_replicas": 3,
            "labels": {"app": "test-app"},
            "pods": []
        }
        
        result = list_all_deployments(apps_v1, core_v1, ["kube-system"])
    
    assert len(result) == 1
    assert result[0]["name"] == "test-deployment"
    assert result[0]["namespace"] == "test-namespace"
    
    apps_v1.list_deployment_for_all_namespaces.assert_called_once()
    mock_process.assert_called_once_with(deployment, apps_v1, core_v1)


def test_list_all_deployments_skip_protected():
    """Test de list_all_deployments avec un namespace protégé"""
    apps_v1 = MagicMock()
    core_v1 = MagicMock()
    
    deployment = MagicMock()
    deployment.metadata.name = "test-deployment"
    deployment.metadata.namespace = "kube-system"
    
    deployments = MagicMock()
    deployments.items = [deployment]
    
    apps_v1.list_deployment_for_all_namespaces.return_value = deployments
    
    result = list_all_deployments(apps_v1, core_v1, ["kube-system"])
    
    assert len(result) == 0
    
    apps_v1.list_deployment_for_all_namespaces.assert_called_once()


def test_list_all_deployments_skip_workload_scheduler():
    """Test de list_all_deployments pour ignorer workload-scheduler"""
    apps_v1 = MagicMock()
    core_v1 = MagicMock()
    
    deployment = MagicMock()
    deployment.metadata.name = "workload-scheduler"
    deployment.metadata.namespace = "test-namespace"
    
    deployments = MagicMock()
    deployments.items = [deployment]
    
    apps_v1.list_deployment_for_all_namespaces.return_value = deployments
    
    result = list_all_deployments(apps_v1, core_v1, ["kube-system"])
    
    assert len(result) == 0
    
    apps_v1.list_deployment_for_all_namespaces.assert_called_once()


def test_list_all_deployments_api_exception():
    """Test de list_all_deployments avec une exception de l'API"""
    apps_v1 = MagicMock()
    core_v1 = MagicMock()
    
    from kubernetes.client.exceptions import ApiException
    apps_v1.list_deployment_for_all_namespaces.side_effect = ApiException("API Error")
    
    result = list_all_deployments(apps_v1, core_v1, ["kube-system"])
    
    assert "status" in result
    assert result["status"] == "error"
    assert "message" in result
    assert "API Error" in result["message"]


def test_meets_sts_criteria(mock_statefulset):
    """Test de meets_sts_criteria"""
    result = meets_sts_criteria(mock_statefulset, ["kube-system"])
    
    assert result is True
    
    mock_statefulset.metadata.namespace = "kube-system"
    result = meets_sts_criteria(mock_statefulset, ["kube-system"])
    
    assert result is False
    
    mock_statefulset.metadata.namespace = "test-namespace"
    mock_statefulset.metadata.labels = {"app": "test-app"}
    result = meets_sts_criteria(mock_statefulset, ["kube-system"])
    
    assert result is False
    
    mock_statefulset.metadata.labels = None
    result = meets_sts_criteria(mock_statefulset, ["kube-system"])
    
    assert result is False


def test_process_statefulset(mock_statefulset):
    """Test de process_statefulset"""
    core_v1 = MagicMock()
    
    pod = MagicMock()
    pod.metadata.name = "test-pod"
    pod.metadata.owner_references = [MagicMock()]
    pod.metadata.owner_references[0].kind = "StatefulSet"
    pod.metadata.owner_references[0].uid = "test-sts-uid"
    
    pods = MagicMock()
    pods.items = [pod]
    
    core_v1.list_namespaced_pod.return_value = pods
    
    result = process_statefulset(mock_statefulset, core_v1)
    
    assert result["namespace"] == "test-namespace"
    assert result["name"] == "test-statefulset"
    assert result["uid"] == "test-sts-uid"
    assert result["replicas"] == 3
    assert result["available_replicas"] == 3
    assert result["ready_replicas"] == 3
    assert "argocd.argoproj.io/instance" in result["labels"]
    assert len(result["pods"]) == 1
    
    core_v1.list_namespaced_pod.assert_called_once_with("test-namespace", watch=False)


def test_list_all_sts():
    """Test de list_all_sts"""
    apps_v1 = MagicMock()
    core_v1 = MagicMock()
    
    statefulset = MagicMock()
    statefulset.metadata.name = "test-statefulset"
    statefulset.metadata.namespace = "test-namespace"
    statefulset.metadata.labels = {
        "app": "test-app",
        "argocd.argoproj.io/instance": "test-instance"
    }
    
    statefulsets = MagicMock()
    statefulsets.items = [statefulset]
    
    apps_v1.list_stateful_set_for_all_namespaces.return_value = statefulsets
    
    # Here's the important change, using the correct module path:
    with patch('core.kub_list.process_statefulset') as mock_process:
        mock_process.return_value = {
            "namespace": "test-namespace",
            "name": "test-statefulset",
            "uid": "test-sts-uid",
            "replicas": 3,
            "available_replicas": 3,
            "ready_replicas": 3,
            "labels": {
                "app": "test-app",
                "argocd.argoproj.io/instance": "test-instance"
            },
            "pods": []
        }
        
        result = list_all_sts(apps_v1, core_v1, ["kube-system"])
    
    assert len(result) == 1
    assert result[0]["name"] == "test-statefulset"
    assert result[0]["namespace"] == "test-namespace"
    
    apps_v1.list_stateful_set_for_all_namespaces.assert_called_once()
    mock_process.assert_called_once_with(statefulset, core_v1)


def test_list_all_sts_skip_no_label():
    """Test de list_all_sts avec un StatefulSet sans le label requis"""
    apps_v1 = MagicMock()
    core_v1 = MagicMock()
    
    statefulset = MagicMock()
    statefulset.metadata.name = "test-statefulset"
    statefulset.metadata.namespace = "test-namespace"
    statefulset.metadata.labels = {"app": "test-app"}
    
    statefulsets = MagicMock()
    statefulsets.items = [statefulset]
    
    apps_v1.list_stateful_set_for_all_namespaces.return_value = statefulsets
    
    result = list_all_sts(apps_v1, core_v1, ["kube-system"])
    
    assert len(result) == 0
    
    apps_v1.list_stateful_set_for_all_namespaces.assert_called_once()


def test_list_all_sts_api_exception():
    """Test de list_all_sts avec une exception de l'API"""
    apps_v1 = MagicMock()
    core_v1 = MagicMock()
    
    from kubernetes.client.exceptions import ApiException
    apps_v1.list_stateful_set_for_all_namespaces.side_effect = ApiException("API Error")
    
    result = list_all_sts(apps_v1, core_v1, ["kube-system"])
    
    assert "status" in result
    assert result["status"] == "error"
    assert "message" in result
    assert "API Error" in result["message"]
