# Protected namespaces and label criteria
protected_namespaces = [
    "kube-system",
    # "default",
    "kube-public",
    "longhorn-system",
    # "keeper",
]
shutdown_label_selector = 'shutdown="false"'
