from owlready2 import get_ontology, default_world, onto_path # <-- Import onto_path
import argparse
import yaml
import docker_functions
import kubernetes_functions
import os # <-- Import os
# -------------------------------
# Parse command-line arguments
# -------------------------------
parser = argparse.ArgumentParser(description="OWL Ontology Validator")
parser.add_argument("--classes", required=True, help="Path to the class (TBox) OWL file")
parser.add_argument("--instances", required=True, help="Path to the instance (ABox) OWL file")
args = parser.parse_args()

CLASS_FILE = args.classes
INSTANCE_FILE = args.instances


ontology_dir = os.path.dirname(CLASS_FILE)
if ontology_dir and ontology_dir not in onto_path:
    onto_path.append(ontology_dir)
# --- New Code Ends Here ---

print("Loading Classes...")
# The TBox file is loaded first, so its imports (if any) are resolved.
onto = get_ontology(CLASS_FILE).load()

print("Loading Instances...")
# The ABox file is loaded, and it will now search the directory in onto_path
# for its imports (like 'entity.owx').
instances_onto = get_ontology(INSTANCE_FILE).load()
onto.imported_ontologies.append(instances_onto)

print("\nLoaded ontologies:")
print(" Classes:", onto.base_iri)
print(" Instances:", instances_onto.base_iri)


all_instances = list(default_world.individuals())


def find_platform_type():
    kubernetes_deployment_plan = False
    docker_deployment_plan = False

    DOCKER_IDENTIFIERS = {"2024.Docker_Compose", "2024.Docker_Swarm", "2024.Docker_Engine", "2024.Docker"}

    for instance in all_instances:
        # Get the string representation of the instance (e.g., "2024.Docker")
        instance_str = str(instance)

        # 1. CORRECT DOCKER CHECK
        if instance_str in DOCKER_IDENTIFIERS:
            docker_deployment_plan = True

        # 2. CORRECT KUBERNETES CHECK
        if instance_str == "2024.Kubernetes":
            kubernetes_deployment_plan = True

        # Optimization: Stop early if both are found
        if docker_deployment_plan and kubernetes_deployment_plan:
            break

    return kubernetes_deployment_plan, docker_deployment_plan


# After this correction, the output should be (True, True) because both
# '2024.Docker' and '2024.Kubernetes' exist in your all_instances list.

print("\nAll instances in ontology:")
for inst in all_instances:
    print(" -", inst)

os.makedirs("../generated_files", exist_ok=True)
kubernetes_deployment_plan, docker_deployment_plan = find_platform_type()
print(kubernetes_deployment_plan,docker_deployment_plan)
if kubernetes_deployment_plan:
    print("Generate Kubernetes deployment plan")
    pods_list = kubernetes_functions.find_kubernetes_instances(all_instances)
    kubernetes_functions.find_kubernetes_data_assertions(pods_list, onto)
    namespace, deployments, volumes,pvcs, = kubernetes_functions.generate_kubernetes_yaml_files(pods_list, onto)
    deployment_counter=0
    volume_counter=0
    pvc_counter=0
    for deployment in deployments:
        deployment_counter = deployment_counter +1
        with open("../generated_files/kubernetes-deployment"+str(deployment_counter)+".generated.yml", "w") as f:
            yaml.dump(deployment, f, sort_keys=False)
    with open("../generated_files/kubernetes-namespace.generated.yml", "w") as f:
        yaml.dump(namespace, f, sort_keys=False)
    for volume in volumes:
        volume_counter = volume_counter +1
        with open("../generated_files/kubernetes-volume"+str(volume_counter)+".generated.yml", "w") as f:
            yaml.dump(volume, f, sort_keys=False)
    for pvc in pvcs:
        pvc_counter = pvc_counter +1
        with open("../generated_files/kubernetes-pvc"+str(pvc_counter)+".generated.yml", "w") as f:
            yaml.dump(pvc, f, sort_keys=False)
    print("Generated Kubernetes files")
if docker_deployment_plan:
    print("Generate Docker deployment plan")
    container_list = docker_functions.find_docker_instances(all_instances)
    docker_functions.find_docker_data_assertions(container_list, onto)
    compose = docker_functions.generate_docker_compose(container_list, onto)

    with open("../generated_files/docker-compose.generated.yml", "w") as f:
        yaml.dump(compose, f, sort_keys=False)

    print("Generated Docker Compose file")
