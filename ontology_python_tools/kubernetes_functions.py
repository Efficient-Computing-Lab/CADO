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
# ----------------------------------------------------------
# 3. GENERATE KUBERNETES YAML FILES (FIXED LOGIC)
# ----------------------------------------------------------
def generate_kubernetes_yaml_files(container_list, onto):
    resources = {
        "namespaces": set(),
        "deployments": [],
        "volumes": {}
    }
    # Temporary structure to hold all pod/deployment config data
    deployment_configs = {}

    data_props = {prop.name.lower(): prop for prop in onto.data_properties()}

    # =======================================================
    # PASS 1: AGGREGATE ALL DATA (VOLUMES AND DEPLOYMENT CONFIGS)
    # =======================================================
    for inst in container_list:
        ont_name = inst.name
        prefix = ont_name.split("_")[0]

        # --- Common Data Extraction ---
        instance_data = {}
        for prop_name, prop in data_props.items():
            values = list(getattr(inst, prop.python_name, []))
            if not values:
                continue
            instance_data[prop_name] = values[0]

        # -------------------------------------------------------
        # PARSE VOLUME DATA (Store in resources["volumes"])
        # -------------------------------------------------------
        if "volume" in ont_name.lower():
            if instance_data.get("volume_name"):
                resources["volumes"][prefix] = {
                    "name": instance_data["volume_name"],
                    "hostPath": instance_data.get("volume_host_path"),
                    "storage": instance_data.get("reserved_storage") or "1Gi",
                    "accessMode": "ReadWriteOnce"
                }

        # -------------------------------------------------------
        # PARSE POD DATA (Store in temporary deployment_configs)
        # -------------------------------------------------------
        elif "pod" in ont_name.lower():
            deployment_name = instance_data.get("deployment_name")
            if deployment_name:

                # Initialize config for this deployment if it doesn't exist
                if deployment_name not in deployment_configs:
                    deployment_configs[deployment_name] = {
                        "namespace_name": "default",
                        "replicas_value": 1,
                        "containers": [],  # List to support multi-container pods if needed
                        "volume_mounts": []
                    }

                config = deployment_configs[deployment_name]

                # Deployment Metadata
                config["namespace_name"] = instance_data.get("related_namespace", config["namespace_name"])
                resources["namespaces"].add(config["namespace_name"])
                try:
                    config["replicas_value"] = int(instance_data.get("replicas", config["replicas_value"]))
                except (ValueError, TypeError):
                    pass  # Keep default if conversion fails

                # Container Spec
                container_spec = {}
                env_vars = []

                if instance_data.get("container_name"):
                    container_spec["name"] = instance_data["container_name"]
                if instance_data.get("related_image"):
                    container_spec["image"] = instance_data["related_image"]

                for prop_name, value in instance_data.items():
                    if prop_name.startswith("env_"):
                        key = prop_name.replace("env_", "").upper()
                        env_vars.append({"name": key, "value": value})

                # Volume Mounts (store *which* pod/deployment/volume connection this is)
                if instance_data.get("volume_mount_path"):
                    config["volume_mounts"].append({
                        "prefix": prefix,  # Use the prefix to link to the volume data later
                        "mountPath": instance_data["volume_mount_path"]
                    })

                # Dedup and add container
                if container_spec:
                    dedup = {e["name"]: e["value"] for e in env_vars}
                    container_spec["env"] = [{"name": k, "value": v} for k, v in dedup.items()]
                    config["containers"].append(container_spec)

    # =======================================================
    # PASS 2: GENERATE YAML RESOURCES
    # =======================================================

    # -------------------------------------------------------
    # BUILD DEPLOYMENTS
    # -------------------------------------------------------
    for deployment_name, config in deployment_configs.items():

        container_blocks = []
        for container_spec in config["containers"]:
            container_block = dict(container_spec)

            # Add volumeMounts to the container block
            volume_mounts = []
            for vm_data in config["volume_mounts"]:
                # Link volume mount to the volume data using the prefix
                prefix = vm_data["prefix"]
                if prefix in resources["volumes"]:
                    vol = resources["volumes"][prefix]
                    volume_mounts.append({"name": vol["name"], "mountPath": vm_data["mountPath"]})

            if volume_mounts:
                container_block["volumeMounts"] = volume_mounts

            container_blocks.append(container_block)

        template_spec = {"containers": container_blocks}

        # Add Volume specs (PVCs) to the Pod Template
        pod_volumes = []
        # Check all volume mounts for the deployment and add a volume spec for each unique volume
        used_volumes = set()
        for vm_data in config["volume_mounts"]:
            prefix = vm_data["prefix"]
            if prefix in resources["volumes"] and prefix not in used_volumes:
                vol = resources["volumes"][prefix]
                pod_volumes.append({
                    "name": vol["name"],
                    "persistentVolumeClaim": {"claimName": vol["name"]+"c"}
                })
                used_volumes.add(prefix)

        if pod_volumes:
            template_spec["volumes"] = pod_volumes

        # Assume single container for selector label for simplicity
        app_label = config["containers"][0]["name"] if config["containers"] else deployment_name

        deployment = {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": deployment_name, "namespace": config["namespace_name"]},
            "spec": {
                "replicas": config["replicas_value"],
                "selector": {"matchLabels": {"app": app_label}},
                "template": {
                    "metadata": {"labels": {"app": app_label}},
                    "spec": template_spec
                }
            }
        }
        resources["deployments"].append(deployment)

    # -------------------------------------------------------
    # NAMESPACE, PV, PVC (This section remains largely the same)
    # -------------------------------------------------------
    # ... (remaining logic for NS, PV, PVC as in the original code)
    ns = None
    namespaces = sorted({n for n in resources["namespaces"] if n.lower() != "default"})
    if namespaces:
        print(namespaces)
        ns = {"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": namespaces[0]}}

    pv_array = []
    pvc_array = []
    for prefix, v in resources["volumes"].items():
        # PersistentVolume
        pv = {
            "apiVersion": "v1",
            "kind": "PersistentVolume",
            "metadata": {"name": v["name"], "namespace":namespaces[0]},
            "spec": {
                "capacity": {"storage": v["storage"]},
                "accessModes": [v["accessMode"]],
                "hostPath": {"path": v["hostPath"]},
            }
        }
        pv_array.append(pv)

        # PersistentVolumeClaim
        pvc = {
            "apiVersion": "v1",
            "kind": "PersistentVolumeClaim",
            "metadata": {"name": v["name"]+"c","namespace":namespaces[0]},
            "spec": {
                "accessModes": [v["accessMode"]],
                "resources": {"requests": {"storage": v["storage"]}},
                "storageClassName": ""
            }
        }
        pvc_array.append(pvc)

    return ns, resources["deployments"], pv_array, pvc_array
