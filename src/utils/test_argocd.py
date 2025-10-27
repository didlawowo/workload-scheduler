from argocd import (
    enable_auto_sync,
    get_argocd_session_token,
    verify_argocd_session_token,
)

# from argocd_token import ArgocdClient
from icecream import ic

# argo_token = ArgocdClient.get_argocd_token()

def test_get_argocd_session_token():
    # ic(get_argocd_session_token())
    # ic(argo_token)
    verify_argocd_session_token(get_argocd_session_token())
    enable_auto_sync("workload")

test_get_argocd_session_token()