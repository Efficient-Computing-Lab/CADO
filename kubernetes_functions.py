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
        if "Pod" in inst.name:
            container_list.append(inst)
            continue

        # Class-based match
        for cls in inst.is_a:
            if "Pod" in cls.name:
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
        found_props = False

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

        if not found_props:
            print("  No Kubernetes-relevant data properties found.")


# ----------------------------------------------------------
# 3. GENERATE KUBERNETES YAML FILES (FIXED TO RETURN ARRAYS AND SINGLE NAMESPACE)
# ----------------------------------------------------------
def generate_kubernetes_yaml_files(container_list, onto):
    """
    Generates Namespace, Deployment, and PersistentVolume resources.

    Returns:
        tuple: (namespace_dict, deployment_array, volume_array)
    """

    resources = {
        "namespaces": set(),
        "deployments": [],
        "volumes": {}
    }

    # CACHE data properties once
    data_props = {prop.name.lower(): prop for prop in onto.data_properties()}

    # -------------------------------------------
    # Resource Collection (Mostly unchanged)
    # -------------------------------------------
    for inst in container_list:
        # Fields
        container_spec = {}
        env_vars = []
        volume_mounts = []
        pod_volumes = []

        deployment_name = None
        namespace_name = "default"
        replicas_value = 1

        # Extract data property values
        for prop_name, prop in data_props.items():
            values = list(getattr(inst, prop.python_name, []))
            if not values:
                continue

            if prop_name == "deployment_name":
                deployment_name = values[0]
            elif prop_name == "container_name":
                container_spec["name"] = values[0]
            elif prop_name == "related_image":
                container_spec["image"] = values[0]
            elif prop_name == "related_namespace":
                namespace_name = values[0]
                resources["namespaces"].add(namespace_name)
            elif prop_name == "replicas":
                try:
                    replicas_value = int(values[0])
                except ValueError:
                    print(f"Warning: Non-integer replicas value '{values[0]}' for {inst.name}. Defaulting to 1.")
                    replicas_value = 1
            elif prop_name.startswith("env_"):
                key = prop_name.replace("env_", "").upper()
                env_vars.append({"name": key, "value": values[0]})

        # Handle Volume Binding Logic (Corrected property access: "#binds" to "binds" for safety)
        volume_objects = list(getattr(inst, "#binds", []))
        mount_paths = list(getattr(inst, "volume_mount_path", []))

        for i, volume_inst in enumerate(volume_objects):
            vol_name = getattr(volume_inst, "volume_name", [])
            host_path = getattr(volume_inst, "volume_host_path", [])
            storage = getattr(volume_inst, "reserved_storage", [])

            if vol_name and host_path and i < len(mount_paths):
                vname = vol_name[0]
                hpath = host_path[0]
                mpath = mount_paths[i]

                # Kubernetes container volumeMounts
                volume_mounts.append({"name": vname, "mountPath": mpath})
                # Kubernetes Pod volumes (HostPath for simplicity)
                pod_volumes.append({"name": vname, "hostPath": {"path": hpath}})

                # Kubernetes PersistentVolume spec (collected once per unique volume)
                resources["volumes"][vname] = {
                    "hostPath": hpath,
                    "storage": storage[0] if storage else "1Gi",
                    "accessMode": "ReadWriteOnce"
                }

        # Build Deployment YAML
        if deployment_name:
            container_block = dict(container_spec)
            if env_vars:
                container_block["env"] = env_vars
            if volume_mounts:
                container_block["volumeMounts"] = volume_mounts

            template_spec = {"containers": [container_block]}
            if pod_volumes:
                template_spec["volumes"] = pod_volumes

            app_label = container_spec.get("name") or deployment_name

            deployment = {
                "apiVersion": "apps/v1",
                "kind": "Deployment",
                "metadata": {
                    "name": deployment_name,
                    "namespace": namespace_name
                },
                "spec": {
                    "replicas": replicas_value,
                    "selector": {
                        "matchLabels": {
                            "app": app_label
                        }
                    },
                    "template": {
                        "metadata": {
                            "labels": {
                                "app": app_label
                            }
                        },
                        "spec": template_spec
                    }
                }
            }
            resources["deployments"].append(deployment)

    # ---------------------------------------
    # Final Structure Generation (The requested change)
    # ---------------------------------------

    # 1. NAMESPACE (Single Dict)
    # Get the first non-default namespace collected, or None
    unique_namespaces = sorted([ns for ns in resources["namespaces"] if ns.lower() != "default"])

    if unique_namespaces:
        single_namespace_name = unique_namespaces[0]
        namespace_doc = {
            "apiVersion": "v1",
            "kind": "Namespace",
            "metadata": {"name": single_namespace_name}
        }
    else:
        namespace_doc = None  # Or you could return a dict for 'default' if preferred

    # 2. DEPLOYMENTS (Array of Dicts)
    # The resources["deployments"] is already the desired array structure.
    deployment_array = resources["deployments"]

    # 3. VOLUMES (Array of PersistentVolume Dicts)
    volume_array = []
    for vname, vinfo in resources["volumes"].items():
        volume_doc = {
            "apiVersion": "v1",
            "kind": "PersistentVolume",
            "metadata": {"name": vname},
            "spec": {
                "capacity": {"storage": vinfo.get("storage", "1Gi")},
                "accessModes": [vinfo.get("accessMode", "ReadWriteOnce")],
                # Assuming HostPath based on your previous logic
                "hostPath": {"path": vinfo["hostPath"]}
            }
        }
        volume_array.append(volume_doc)

    return namespace_doc, deployment_array, volume_array