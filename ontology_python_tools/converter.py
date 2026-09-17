"""
CADO converter: transforms a CADO deployment description into the deployment
artifacts of a concrete container platform.

The converter selects a serialisation backend from the artifact_format property
declared by each platform individual in the ontology; it never inspects the
names of individuals. Adding support for a new platform means registering a new
backend below and asserting the corresponding artifact_format in the A-Box.

Usage:
    python converter.py --classes ../ontology_files/entity.owx \
                        --instances ../ontology_files/instances.owl
"""

import argparse
import os

import yaml
from owlready2 import get_ontology, default_world, onto_path, sync_reasoner

import cado_graph as g
import docker_functions
import kubernetes_functions

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_OUTPUT_DIR = os.path.join(REPO_ROOT, "generated_files")


def load(class_file, instance_file, reason=True):
    ontology_dir = os.path.dirname(os.path.abspath(class_file))
    if ontology_dir not in onto_path:
        onto_path.append(ontology_dir)

    print("Loading T-Box ...")
    tbox = get_ontology(os.path.abspath(class_file)).load()
    print("Loading A-Box ...")
    abox = get_ontology(os.path.abspath(instance_file)).load()

    if reason:
        print("Running reasoner (HermiT) ...")
        with abox:
            sync_reasoner(infer_property_values=True, debug=0)
        print("Ontology is consistent; inferences materialised.")
    return tbox, abox


def write(directory, filename, document):
    path = os.path.join(directory, filename)
    with open(path, "w") as handle:
        yaml.dump(document, handle, sort_keys=False)
    return path


def emit_docker_compose(tbox, world, platform, out_dir):
    docker_functions.describe(tbox, world, platform)
    compose = docker_functions.generate_docker_compose(tbox, world, platform)
    return [write(out_dir, "docker-compose.generated.yml", compose)]


def emit_kubernetes_manifests(tbox, world, platform, out_dir):
    kubernetes_functions.describe(tbox, world, platform)
    namespace, deployments, volumes, claims = \
        kubernetes_functions.generate_kubernetes_manifests(tbox, world, platform)

    written = []
    if namespace:
        written.append(write(out_dir, "kubernetes-namespace.generated.yml", namespace))
    for index, deployment in enumerate(deployments, start=1):
        written.append(write(out_dir, "kubernetes-deployment%d.generated.yml" % index, deployment))
    for index, volume in enumerate(volumes, start=1):
        written.append(write(out_dir, "kubernetes-volume%d.generated.yml" % index, volume))
    for index, claim in enumerate(claims, start=1):
        written.append(write(out_dir, "kubernetes-pvc%d.generated.yml" % index, claim))
    return written


# artifact_format value -> backend. The only place platform knowledge lives.
BACKENDS = {
    "docker-compose": emit_docker_compose,
    "kubernetes-manifest": emit_kubernetes_manifests,
}


def main():
    parser = argparse.ArgumentParser(description="CADO deployment artifact converter")
    parser.add_argument("--classes", required=True, help="Path to the T-Box OWL file")
    parser.add_argument("--instances", required=True, help="Path to the A-Box OWL file")
    parser.add_argument("--out", default=DEFAULT_OUTPUT_DIR, help="Output directory")
    parser.add_argument("--no-reasoner", action="store_true",
                        help="Skip reasoning (uses only asserted axioms)")
    args = parser.parse_args()

    tbox, _ = load(args.classes, args.instances, reason=not args.no_reasoner)
    os.makedirs(args.out, exist_ok=True)

    platforms = g.target_platforms(tbox, default_world)
    if not platforms:
        print("\nNo platform declares an artifact_format; nothing to generate.")
        return

    print("\nTarget platforms found in the ontology:")
    for platform in platforms:
        print("  - %s -> %s" % (platform.name, g.one(platform, "artifact_format")))

    generated = []
    for platform in platforms:
        artifact_format = g.one(platform, "artifact_format")
        backend = BACKENDS.get(artifact_format)
        if backend is None:
            print("\nNo backend registered for artifact_format '%s' (platform %s); skipped."
                  % (artifact_format, platform.name))
            continue
        generated.extend(backend(tbox, default_world, platform, args.out))

    print("\nGenerated %d file(s) in %s:" % (len(generated), args.out))
    for path in sorted(generated):
        print("  -", os.path.basename(path))


if __name__ == "__main__":
    main()
