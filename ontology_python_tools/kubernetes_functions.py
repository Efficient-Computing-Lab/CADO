# kube_generator.py
import yaml
from owlready2 import get_ontology, default_world


# ----------------------------------------------------------
# 1. FIND KUBERNETES POD INSTANCES (UNCHANGED)
# ----------------------------------------------------------
def find_kubernetes_instances(all_instances):
    # ... (unchanged)
    container_list = []


    for inst in all_instances:

        # Direct name match
        if "Pod" in inst.name or "Kubernetes_Volume" in inst.name:
            container_list.append(inst)
            continue

        # Class-based match
        for cls in inst.is_a:
            if "Pod" in cls.name or "Kubernetes_Volume" in inst.name:
                container_list.append(inst)
                break
    print("\nPod instances found:")
    for inst in container_list:
        print(" -", inst)
    return container_list


# ----------------------------------------------------------
# 2. FIND KUBERNETES DATA ASSERTIONS (UNCHANGED)
# ----------------------------------------------------------
# ----------------------------------------------------------
# 2. FIND KUBERNETES DATA ASSERTIONS (REVISED FOR ROBUSTNESS)
# ----------------------------------------------------------
def find_kubernetes_data_assertions(container_list, onto):
    """
    Prints data properties asserted on Pod instances, handling potential
    Owlready2 naming inconsistencies.
    """
    print("\nData assertions for Pod instances:\n")

    for inst in container_list:
        print(f"Instance: {inst.name}")

        # 1. Iterate over all defined data properties in the ontology
        for prop in onto.data_properties():

            # --- Attempt 1: Use Owlready2's designated Python property name ---
            values = getattr(inst, prop.python_name, [])

            # --- Attempt 2: Use the raw property name (local name) if attempt 1 fails ---
            # This is common if the ontology doesn't set a python_name correctly.
            if not values:
                values = getattr(inst, prop.name, [])

            # Convert values to a list if not already (for consistency)
            if values:
                # Use list(values) to handle case where values is a generator/set
                print(f"  {prop.name} -> {list(values)}")
                found_props = True





# ----------------------------------------------------------
# 3. GENERATE KUBERNETES YAML FILES (FIXED TO RETURN ARRAYS AND SINGLE NAMESPACE)
# ----------------------------------------------------------
def generate_kubernetes_yaml_files(container_list, onto):
    resources = {
        "namespaces": set(),
        "deployments": [],
        "volumes": {}
    }

    data_props = {prop.name.lower(): prop for prop in onto.data_properties()}

    for inst in container_list:
        ont_name = inst.name

        container_spec = {}
        env_vars = []
        volume_mounts = []
        pod_volumes = []

        deployment_name = None
        namespace_name = "default"
        replicas_value = 1

        volume_name = None
        storage = None
        host_path = None

        # -------------------------------------------------------
        # PARSE POD DATA
        # -------------------------------------------------------
        if "pod" in ont_name.lower():
            for prop_name, prop in data_props.items():
                values = list(getattr(inst, prop.python_name, []))
                if not values:
                    continue

                value = values[0]

                if prop_name == "deployment_name":
                    deployment_name = value

                elif prop_name == "container_name":
                    container_spec["name"] = value

                elif prop_name == "related_image":
                    container_spec["image"] = value

                elif prop_name == "related_namespace":
                    namespace_name = value
                    resources["namespaces"].add(value)

                elif prop_name == "replicas":
                    replicas_value = int(value)

                elif prop_name.startswith("env_"):
                    key = prop_name.replace("env_", "").upper()
                    env_vars.append({"name": key, "value": value})

                elif prop_name == "volume_mount_path":
                    volume_mounts.append({
                        "pod_prefix": ont_name.split("_")[0],
                        "mountPath": value
                    })

        # -------------------------------------------------------
        # PARSE VOLUME DATA
        # -------------------------------------------------------
        if "volume" in ont_name.lower():
            prefix = ont_name.split("_")[0]

            for prop_name, prop in data_props.items():
                values = list(getattr(inst, prop.python_name, []))
                if not values:
                    continue

                value = values[0]

                if prop_name == "volume_name":
                    volume_name = value

                elif prop_name == "reserved_storage":
                    storage = value

                elif prop_name == "volume_host_path":
                    host_path = value

            if volume_name and host_path:
                resources["volumes"][prefix] = {
                    "name": volume_name,
                    "hostPath": host_path,
                    "storage": storage or "1Gi",
                    "accessMode": "ReadWriteOnce"
                }

        # -------------------------------------------------------
        # BUILD DEPLOYMENT
        # -------------------------------------------------------
        if deployment_name:
            # Deduplicate env vars
            dedup = {}
            for e in env_vars:
                dedup[e["name"]] = e["value"]
            env_vars = [{"name": k, "value": v} for k, v in dedup.items()]

            container_block = dict(container_spec)

            if env_vars:
                container_block["env"] = env_vars

            # Match volumeMounts to volumes
            prefix = ont_name.split("_")[0]
            if prefix in resources["volumes"]:
                vol = resources["volumes"][prefix]
                volume_mounts = [{"name": vol["name"], "mountPath": vm["mountPath"]} for vm in volume_mounts]

            if volume_mounts:
                container_block["volumeMounts"] = volume_mounts

            template_spec = {"containers": [container_block]}

            if prefix in resources["volumes"]:
                v = resources["volumes"][prefix]
                template_spec["volumes"] = [{
                    "name": v["name"],
                    "hostPath": {"path": v["hostPath"]}
                }]

            deployment = {
                "apiVersion": "apps/v1",
                "kind": "Deployment",
                "metadata": {"name": deployment_name, "namespace": namespace_name},
                "spec": {
                    "replicas": replicas_value,
                    "selector": {"matchLabels": {"app": container_spec["name"]}},
                    "template": {
                        "metadata": {"labels": {"app": container_spec["name"]}},
                        "spec": template_spec
                    }
                }
            }

            resources["deployments"].append(deployment)

    # -------------------------------------------------------
    # NAMESPACE
    # -------------------------------------------------------
    ns = None
    namespaces = sorted({n for n in resources["namespaces"] if n.lower() != "default"})
    if namespaces:
        ns = {"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": namespaces[0]}}

    # -------------------------------------------------------
    # PV
    # -------------------------------------------------------
    volume_array = []
    for prefix, v in resources["volumes"].items():
        pv = {
            "apiVersion": "v1",
            "kind": "PersistentVolume",
            "metadata": {"name": v["name"]},
            "spec": {
                "capacity": {"storage": v["storage"]},
                "accessModes": [v["accessMode"]],
                "hostPath": {"path": v["hostPath"]},
            }
        }
        volume_array.append(pv)

    return ns, resources["deployments"], volume_array
