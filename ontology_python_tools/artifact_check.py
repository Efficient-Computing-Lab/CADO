"""
Structural validation of generated deployment artifacts.

kubectl needs a reachable API server even for a client-side dry run, so this
module provides an offline check of the artifacts CADO produces: required keys,
well-formed references between resources, and internal consistency (for example,
that every volumeMount names a volume the pod actually declares).

    python artifact_check.py ../generated_files ../generated_files/microservice
"""

import os
import sys

import yaml

REQUIRED_BY_KIND = {
    "Namespace": [],
    "PersistentVolume": ["spec.capacity.storage", "spec.accessModes"],
    "PersistentVolumeClaim": ["spec.accessModes", "spec.resources.requests.storage"],
    "Deployment": ["spec.replicas", "spec.selector.matchLabels",
                   "spec.template.spec.containers"],
}


def dig(document, path):
    current = document
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def check_compose(path, errors):
    document = yaml.safe_load(open(path))
    services = document.get("services")
    if not services:
        errors.append("%s: no services" % path)
        return

    declared_networks = set(document.get("networks") or {})
    declared_volumes = set(document.get("volumes") or {})

    for name, service in services.items():
        if "image" not in service:
            errors.append("%s: service '%s' has no image" % (path, name))
        for network in service.get("networks", []):
            if network not in declared_networks:
                errors.append("%s: service '%s' uses undeclared network '%s'"
                              % (path, name, network))
        for volume in service.get("volumes", []):
            volume_name = str(volume).split(":")[0]
            if volume_name not in declared_volumes:
                errors.append("%s: service '%s' uses undeclared volume '%s'"
                              % (path, name, volume_name))
        for dependency in service.get("depends_on", []):
            if dependency not in services:
                errors.append("%s: service '%s' depends on unknown service '%s'"
                              % (path, name, dependency))
        limits = dig(service, "deploy.resources.limits") or {}
        if "cpus" in limits and not isinstance(limits["cpus"], (int, float)):
            errors.append("%s: service '%s' cpus limit %r is not numeric"
                          % (path, name, limits["cpus"]))


def check_kubernetes(path, errors, claims):
    document = yaml.safe_load(open(path))
    kind = document.get("kind")
    if not document.get("apiVersion") or not kind:
        errors.append("%s: missing apiVersion or kind" % path)
        return
    if not dig(document, "metadata.name"):
        errors.append("%s: missing metadata.name" % path)

    for required in REQUIRED_BY_KIND.get(kind, []):
        if dig(document, required) is None:
            errors.append("%s: %s missing %s" % (path, kind, required))

    if kind == "PersistentVolumeClaim":
        claims.add(dig(document, "metadata.name"))

    if kind != "Deployment":
        return

    pod_spec = dig(document, "spec.template.spec") or {}
    labels = dig(document, "spec.selector.matchLabels") or {}
    template_labels = dig(document, "spec.template.metadata.labels") or {}
    if labels and labels != {k: v for k, v in template_labels.items() if k in labels}:
        errors.append("%s: selector does not match pod template labels" % path)

    volume_names = {v["name"] for v in pod_spec.get("volumes", [])}
    for container in pod_spec.get("containers", []):
        if "image" not in container:
            errors.append("%s: container '%s' has no image" % (path, container.get("name")))
        for mount in container.get("volumeMounts", []):
            if mount["name"] not in volume_names:
                errors.append("%s: container '%s' mounts undeclared volume '%s'"
                              % (path, container.get("name"), mount["name"]))
    for volume in pod_spec.get("volumes", []):
        claim = dig(volume, "persistentVolumeClaim.claimName")
        if claim:
            claims.add(("reference", claim))


def main():
    directories = sys.argv[1:] or ["../generated_files"]
    errors, checked = [], 0

    for directory in directories:
        if not os.path.isdir(directory):
            errors.append("%s: not a directory" % directory)
            continue
        claims = set()
        for entry in sorted(os.listdir(directory)):
            path = os.path.join(directory, entry)
            if not entry.endswith((".yml", ".yaml")):
                continue
            checked += 1
            if "compose" in entry:
                check_compose(path, errors)
            else:
                check_kubernetes(path, errors, claims)

        declared = {c for c in claims if isinstance(c, str)}
        referenced = {c[1] for c in claims if isinstance(c, tuple)}
        for missing in sorted(referenced - declared):
            errors.append("%s: pod references claim '%s' that no PVC declares"
                          % (directory, missing))

    print("Checked %d artifact file(s)" % checked)
    for error in errors:
        print("  ERROR %s" % error)
    print("%d problem(s)" % len(errors))
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
