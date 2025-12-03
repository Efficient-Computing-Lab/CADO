def find_docker_instances(all_instances):
    container_list = []
    for inst in all_instances:
        if "Docker_Container" in inst.name:
            container_list.append(inst)
            continue
        for cls in inst.is_a:
            if "Docker_Container" in cls.name:
                container_list.append(inst)
                break

    print("\nContainer instances found:")
    for inst in container_list:
        print(" -", inst)
    return container_list


def find_docker_data_assertions(container_list, onto):
    print("\nData assertions for container instances:\n")
    for inst in container_list:
        print(f"Instance: {inst}")
        for prop in onto.data_properties():
            values = getattr(inst, prop.python_name, [])
            if values:
                print(f"  {prop.name} -> {values}")


def generate_docker_compose(container_list, onto):
    compose = {
        "version": "3.9",
        "services": {}
    }

    for inst in container_list:
        service_name = inst.name.lower().replace("2024.", "").replace("_docker_container", "")
        service = {}
        env_vars = {}

        # Loop over all data properties
        for prop in onto.data_properties():
            # --- FIX: Use getattr(inst, prop.python_name) for retrieving values ---
            values = getattr(inst, prop.python_name, [])
            # --- END FIX ---

            if not values:
                continue

            # Force convert all values into Python strings
            # Use list(values) to handle potential generator/set returns
            values = [str(v) for v in list(values)]

            prop_name = prop.name.lower()

            if prop_name == "related_image":
                service["image"] = values[0]

            elif prop_name == "container_name":
                service["container_name"] = values[0]

            elif prop_name == "volumes":
                # 'volumes' can be a list of strings (e.g., ["data:/path", "logs:/logs"])
                service["volumes"] = values

            elif prop_name == "networks":
                # 'networks' can be a list of strings (e.g., ["my_net"])
                service["networks"] = values

            elif prop_name == "restart_policy":
                service["restart"] = values[0]

            elif prop_name.startswith("env_"):
                key = prop_name.replace("env_", "").upper()
                service.setdefault("environment", {})  # Ensure 'environment' key exists
                service["environment"][key] = values[0]

        compose["services"][service_name] = service

    # ------------------------------------------------------
    # AUTO-GENERATE NETWORKS AND VOLUMES FROM SERVICES
    # ------------------------------------------------------
    networks = set()
    volumes = set()

    for svc_name, svc in compose["services"].items():
        # Collect networks
        if "networks" in svc:
            for net in svc["networks"]:
                networks.add(net)

        # Collect volumes
        if "volumes" in svc:
            for vol in svc["volumes"]:
                # The format is typically "vol_name:mount_path"
                vol_name = vol.split(":")[0]
                volumes.add(vol_name)

    # Add to compose file
    if networks:
        compose["networks"] = {name: {} for name in networks}

    if volumes:
        compose["volumes"] = {name: {} for name in volumes}

    return compose