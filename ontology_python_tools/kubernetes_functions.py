"""Serialises a CADO platform description into Kubernetes manifests.

This module contains only Kubernetes syntax. Everything it knows about the
deployment comes from cado_graph, i.e. from the ontology.
"""

import cado_graph as g

DEFAULT_ACCESS_MODE = "ReadWriteOnce"
DEFAULT_CAPACITY = "1Gi"


def _claim_name(volume_name):
    return volume_name + "c"


def generate_kubernetes_manifests(onto, world, platform):
    """Returns (namespace, deployments, persistent_volumes, claims)."""
    deployments, namespaces = [], set()

    for unit in g.deployment_units(platform):
        namespace = g.namespace_name(onto, world, unit)
        namespaces.add(namespace)

        container = {}
        container_name = g.one(unit, "container_name") or unit.name.lower()
        container["name"] = container_name

        image = g.image_reference(onto, unit)
        if image:
            container["image"] = image

        environment = g.environment(onto, unit)
        if environment:
            container["env"] = [{"name": k, "value": v} for k, v in environment.items()]

        ports = g.many(unit, "ports")
        if ports:
            container["ports"] = [{"containerPort": int(str(p).split(":")[-1])}
                                  for p in sorted(str(x) for x in ports)]

        # The ephemeral/persistent classification in the ontology decides whether
        # the pod volume is an emptyDir or a persistent volume claim.
        mounts, pod_volumes = [], []
        for storage, mount_path in g.volume_mounts(onto, unit):
            volume_name = g.one(storage, "volume_name")
            if not (volume_name and mount_path):
                continue
            mounts.append({"name": volume_name, "mountPath": mount_path})
            if g.is_a(storage, onto.ephemeral):
                pod_volumes.append({"name": volume_name, "emptyDir": {}})
            else:
                pod_volumes.append({"name": volume_name,
                                    "persistentVolumeClaim": {"claimName": _claim_name(volume_name)}})
        if mounts:
            container["volumeMounts"] = mounts

        limits = {}
        if g.one(unit, "cpu_limit"):
            limits["cpu"] = g.one(unit, "cpu_limit")
        if g.one(unit, "memory_limit"):
            limits["memory"] = g.one(unit, "memory_limit")
        if limits:
            container["resources"] = {"limits": limits}

        pod_spec = {"containers": [container]}
        if pod_volumes:
            pod_spec["volumes"] = pod_volumes

        # A private registry cannot be pulled from anonymously. The ontology
        # states which secret logs in to the registry holding this unit's image,
        # so the reference is emitted only where a credential is actually
        # required. The Secret object itself is created out of band: CADO
        # describes that a credential exists, never the credential material.
        pull_secrets = g.image_pull_secrets(onto, world, unit)
        if pull_secrets:
            pod_spec["imagePullSecrets"] = [{"name": n} for n in pull_secrets]

        replicas = g.one(unit, "replicas", 1)
        deployment_name = g.one(unit, "deployment_name") or container_name

        deployments.append({
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": deployment_name, "namespace": namespace},
            "spec": {
                "replicas": int(replicas),
                "selector": {"matchLabels": {"app": container_name}},
                "template": {
                    "metadata": {"labels": {"app": container_name}},
                    "spec": pod_spec,
                },
            },
        })

    deployments.sort(key=lambda d: d["metadata"]["name"])

    declared = sorted(n for n in namespaces if n != "default")
    namespace_manifest = None
    if declared:
        namespace_manifest = {"apiVersion": "v1", "kind": "Namespace",
                              "metadata": {"name": declared[0]}}
    target_namespace = declared[0] if declared else "default"

    volume_manifests, claim_manifests = [], []
    for storage in g.persistent_volumes(onto, platform):
        volume_name = g.one(storage, "volume_name")
        capacity = g.one(storage, "reserved_storage") or DEFAULT_CAPACITY
        host_path = g.one(storage, "volume_host_path")

        spec = {"capacity": {"storage": capacity},
                "accessModes": [DEFAULT_ACCESS_MODE]}
        if host_path:
            spec["hostPath"] = {"path": host_path}

        volume_manifests.append({
            "apiVersion": "v1", "kind": "PersistentVolume",
            "metadata": {"name": volume_name, "namespace": target_namespace},
            "spec": spec,
        })
        claim_manifests.append({
            "apiVersion": "v1", "kind": "PersistentVolumeClaim",
            "metadata": {"name": _claim_name(volume_name), "namespace": target_namespace},
            "spec": {"accessModes": [DEFAULT_ACCESS_MODE],
                     "resources": {"requests": {"storage": capacity}},
                     "storageClassName": ""},
        })

    return namespace_manifest, deployments, volume_manifests, claim_manifests


def describe(onto, world, platform):
    """Human-readable trace of what was read from the ontology."""
    print("\nPlatform '%s' (artifact_format=%s)" % (platform.name, g.one(platform, "artifact_format")))
    for unit in g.deployment_units(platform):
        print("  deployment unit: %s" % unit.name)
        print("     image           : %s" % g.image_reference(onto, unit))
        print("     namespace       : %s" % g.namespace_name(onto, world, unit))
        print("     replicas        : %s" % g.one(unit, "replicas", 1))
        print("     env             : %s" % g.environment(onto, unit))
        print("     volume mounts   : %s" % [(s.name, p) for s, p in g.volume_mounts(onto, unit)])
        print("     pull secrets    : %s" % g.image_pull_secrets(onto, world, unit))
