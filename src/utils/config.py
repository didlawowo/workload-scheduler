# Protected namespaces and label criteria
protected_namespaces = [
    "kube-system",
    # "default",
    "kube-public",
    "longhorn-system",
    # "keeper",
]

protected_labels = {
    "app.kubernetes.io/part-of": "argocd"
}

shutdown_label_selector = 'shutdown="false"'
