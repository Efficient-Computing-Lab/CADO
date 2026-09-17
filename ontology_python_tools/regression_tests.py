"""
CADO regression and evidence tests.

These tests are the executable form of the claims made about CADO. Each one
either checks that the ontology behaves as specified, or demonstrates a property
that the paper asserts. Run with:

    python regression_tests.py
"""

import os
import re
import sys
import tempfile

import yaml
from owlready2 import (World, onto_path, sync_reasoner,
                       OwlReadyInconsistentOntologyError)

HERE = os.path.dirname(os.path.abspath(__file__))
ONTOLOGY_DIR = os.path.join(os.path.dirname(HERE), "ontology_files")
TBOX = os.path.join(ONTOLOGY_DIR, "entity.owx")
ABOX = os.path.join(ONTOLOGY_DIR, "instances.owl")
ABOX_MICRO = os.path.join(ONTOLOGY_DIR, "instances_microservice.owl")

onto_path.append(ONTOLOGY_DIR)
sys.path.insert(0, HERE)

import cado_graph as g          # noqa: E402
import docker_functions         # noqa: E402
import kubernetes_functions     # noqa: E402

RESULTS = []


def test(name):
    def decorate(function):
        def run():
            try:
                detail = function()
                RESULTS.append((True, name, detail or ""))
            except AssertionError as exc:
                RESULTS.append((False, name, str(exc)))
            except Exception as exc:                       # noqa: BLE001
                RESULTS.append((False, name, "%s: %s" % (type(exc).__name__, exc)))
        run.__name__ = function.__name__
        return run
    return decorate


def load(abox_path, reason=True, extra_axioms=None):
    """Load the ontology into an isolated World so tests cannot interfere."""
    world = World()
    tbox = world.get_ontology(TBOX).load()
    abox = world.get_ontology(abox_path).load()
    if extra_axioms:
        extra_axioms(tbox, abox)
    if reason:
        sync_reasoner(world, infer_property_values=True, debug=0)
    return world, tbox, abox


def artifacts(abox_path):
    world, tbox, _ = load(abox_path)
    output = {}
    for platform in g.target_platforms(tbox, world):
        fmt = g.one(platform, "artifact_format")
        if fmt == "docker-compose":
            output["compose"] = docker_functions.generate_docker_compose(tbox, world, platform)
        elif fmt == "kubernetes-manifest":
            namespace, deployments, volumes, claims = \
                kubernetes_functions.generate_kubernetes_manifests(tbox, world, platform)
            output["k8s"] = {"namespace": namespace, "deployments": deployments,
                             "volumes": volumes, "claims": claims}
    return output


# ---------------------------------------------------------------- T-Box health

@test("T1  T-Box and A-Box are consistent under HermiT")
def t1():
    load(ABOX)
    load(ABOX_MICRO)
    return "both A-Boxes consistent"


@test("T2  No class is unsatisfiable")
def t2():
    world, tbox, _ = load(ABOX)
    unsat = [c.name for c in tbox.classes() if world["http://www.w3.org/2002/07/owl#Nothing"]
             in getattr(c, "equivalent_to", [])]
    assert not unsat, "unsatisfiable: %s" % unsat
    return "%d classes all satisfiable" % len(list(tbox.classes()))


@test("T3  A registry may include an image (v1 could not)")
def t3():
    # In v1 includesImage carried three domain axioms, which OWL reads as an
    # intersection; adding the required disjointness of private and public
    # registries then made every includesImage assertion inconsistent.
    world, tbox, abox = load(ABOX, reason=False)
    with abox:
        registry = tbox.image_registry("test_registry")
        image = tbox.image("test_image")
        registry.includesImage.append(image)
    sync_reasoner(world, debug=0)
    assert tbox.private_image_registry not in registry.INDIRECT_is_a, \
        "registry was silently classified as private"
    assert tbox.public_image_registry not in registry.INDIRECT_is_a, \
        "registry was silently classified as public"
    return "generic image_registry stays generic and consistent"


@test("T4  Composition loops are rejected (composedOf is asymmetric/irreflexive)")
def t4():
    def add_loop(tbox, abox):
        with abox:
            platform = tbox.platform("looping_platform")
            platform.composedOf.append(platform)
    try:
        load(ABOX, extra_axioms=add_loop)
    except OwlReadyInconsistentOntologyError:
        return "p composedOf p correctly rejected"
    raise AssertionError("a platform composed of itself was accepted")


@test("T5  Utilization loops are rejected (utilizes is asymmetric/irreflexive)")
def t5():
    def add_loop(tbox, abox):
        with abox:
            a = tbox.platform("platform_a")
            b = tbox.platform("platform_b")
            a.utilizes.append(b)
            b.utilizes.append(a)
    try:
        load(ABOX, extra_axioms=add_loop)
    except OwlReadyInconsistentOntologyError:
        return "a utilizes b utilizes a correctly rejected"
    raise AssertionError("a utilization cycle was accepted")


@test("T6  No platform is forced to exist by an existential axiom")
def t6():
    source = open(TBOX).read()
    forced = re.findall(r'<ObjectSomeValuesFrom>\s*<ObjectProperty IRI="composedOf"/>', source)
    assert not forced, "composedOf still appears in an existential restriction"
    return "platform no longer entails an infinite composition chain"


# ------------------------------------------------------- the ontology-driven claim

@test("T7  Generated artifacts are invariant under renaming of every individual")
def t7():
    baseline = artifacts(ABOX)

    source = open(ABOX).read()
    renamed = source
    for original, replacement in [("MySQL_Pod", "Alpha_Workload"),
                                  ("Wordpress_Pod", "Beta_Workload"),
                                  ("MySQL_Docker_Container", "Gamma_Runnable"),
                                  ("Wordpress_Docker_Container", "Delta_Runnable"),
                                  ("MySQL_Kubernetes_Volume", "Epsilon_Store"),
                                  ("Wordpress_Kubernetes_Volume", "Zeta_Store"),
                                  ("MySQL_Docker_Volume", "Eta_Store"),
                                  ("Wordpress_Docker_Volume", "Theta_Store"),
                                  ("Namespace", "Eta_Scope"),
                                  ("Network", "Iota_Scope")]:
        renamed = re.sub(r'"%s"' % re.escape(original), '"%s"' % replacement, renamed)

    handle = tempfile.NamedTemporaryFile("w", suffix=".owl", dir=ONTOLOGY_DIR, delete=False)
    handle.write(renamed)
    handle.close()
    try:
        after = artifacts(handle.name)
    finally:
        os.unlink(handle.name)

    assert baseline == after, "renaming individuals changed the generated artifacts"
    return "10 individuals renamed, byte-identical artifacts"


@test("T8  A different deployment needs no T-Box change")
def t8():
    before = open(TBOX).read()
    output = artifacts(ABOX_MICRO)
    assert open(TBOX).read() == before, "the T-Box was modified"
    services = output["compose"]["services"]
    assert set(services) == {"api", "cache", "edge"}, sorted(services)
    assert len(output["k8s"]["deployments"]) == 3
    return "3-tier microservice expressed with the unchanged T-Box"


@test("T9  Ephemeral vs persistent storage produces different artifacts")
def t9():
    output = artifacts(ABOX_MICRO)
    cache = output["compose"]["services"]["cache"]
    assert "tmpfs" in cache and "volumes" not in cache, \
        "ephemeral storage did not become a tmpfs mount"
    api = output["compose"]["services"]["api"]
    assert "volumes" in api, "persistent storage did not become a named volume"

    pods = {d["metadata"]["name"]: d for d in output["k8s"]["deployments"]}
    cache_volumes = pods["cache-deployment"]["spec"]["template"]["spec"]["volumes"]
    assert "emptyDir" in cache_volumes[0], "ephemeral storage did not become an emptyDir"
    api_volumes = pods["api-deployment"]["spec"]["template"]["spec"]["volumes"]
    assert "persistentVolumeClaim" in api_volumes[0], "persistent storage did not become a PVC"
    assert len(output["k8s"]["claims"]) == 1, "an ephemeral volume was given a PVC"
    return "ephemeral -> tmpfs/emptyDir, persistent -> named volume/PVC"


@test("T10 Multiple networks per deployment unit are preserved")
def t10():
    output = artifacts(ABOX_MICRO)
    assert output["compose"]["services"]["api"]["networks"] == ["backend", "frontend"]
    return "api attached to both networks"


@test("T11 Platform-specific unit translation is applied")
def t11():
    output = artifacts(ABOX_MICRO)
    compose_limits = output["compose"]["services"]["api"]["deploy"]["resources"]["limits"]
    assert compose_limits["cpus"] == 0.5, compose_limits
    assert compose_limits["memory"] == "512m", compose_limits

    pods = {d["metadata"]["name"]: d for d in output["k8s"]["deployments"]}
    k8s_limits = pods["api-deployment"]["spec"]["template"]["spec"]["containers"][0]["resources"]["limits"]
    assert k8s_limits == {"cpu": "500m", "memory": "512Mi"}, k8s_limits
    return "500m/512Mi -> Compose 0.5/512m, Kubernetes 500m/512Mi"


@test("T13 A private registry produces an image pull secret, a public one does not")
def t13():
    output = artifacts(ABOX_MICRO)
    pods = {d["metadata"]["name"]: d["spec"]["template"]["spec"]
            for d in output["k8s"]["deployments"]}

    api = pods["api-deployment"]
    assert api["imagePullSecrets"] == [{"name": "registry-credentials"}], \
        "the unit pulling from a private registry got no credential: %s" % api.get("imagePullSecrets")

    for name in ("cache-deployment", "edge-deployment"):
        assert "imagePullSecrets" not in pods[name], \
            "%s pulls from a public registry but was given a credential" % name

    # The first example uses only public registries, so nothing is emitted.
    for deployment in artifacts(ABOX)["k8s"]["deployments"]:
        assert "imagePullSecrets" not in deployment["spec"]["template"]["spec"], \
            "a credential was emitted for a deployment with no private registry"
    return "credential emitted for api only, from loginTo and private_image_registry"


@test("T12 Reasoner-derived facts are used, not just asserted ones")
def t12():
    world, tbox, _ = load(ABOX)
    stateful = sorted(i.name for i in tbox.stateful_deployment_unit.instances())
    assert len(stateful) == 4, stateful
    subplatforms = sorted(i.name for i in tbox.subplatform.instances())
    assert subplatforms == ["Docker", "Docker_Compose"], subplatforms
    bound = [i for i in world.individuals() if g.many(i, "binds")]
    assert len(bound) == 4, [i.name for i in bound]
    return "4 stateful units, 2 subplatforms, 4 binds edges - all inferred"


def main():
    for name, value in sorted(globals().items()):
        if name.startswith("t") and callable(value) and name[1:].isdigit():
            value()
    RESULTS.sort(key=lambda r: r[1])

    print("\nCADO regression and evidence tests")
    print("=" * 72)
    for passed, name, detail in RESULTS:
        print("%s  %s" % ("PASS" if passed else "FAIL", name))
        if detail:
            print("      %s" % detail)
    failures = sum(1 for passed, _, _ in RESULTS if not passed)
    print("=" * 72)
    print("%d passed, %d failed" % (len(RESULTS) - failures, failures))
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
