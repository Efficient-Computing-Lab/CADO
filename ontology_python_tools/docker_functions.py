"""Serialises a CADO platform description into a Docker Compose file.

This module contains only Docker Compose syntax. Everything it knows about the
deployment comes from cado_graph, i.e. from the ontology.
"""

import cado_graph as g

COMPOSE_VERSION = "3.9"


def _compose_cpus(value):
    """Translate a platform-neutral CPU limit into the Compose representation.

    CADO records CPU limits in the Kubernetes-style milli-CPU notation ('500m').
    Compose expects a fractional number of cores, so the value is converted here
    rather than being stored twice in the ontology.
    """
    text = str(value).strip()
    if text.endswith("m"):
        try:
            return round(float(text[:-1]) / 1000.0, 3)
        except ValueError:
            return text
    try:
        return float(text)
    except ValueError:
        return text


def _compose_memory(value):
    """Translate a memory limit into the Compose representation.

    CADO records memory limits with binary IEC suffixes ('512Mi'); Compose uses
    single-letter suffixes with the same 1024 base ('512m').
    """
    text = str(value).strip()
    for iec, compose in (("Ki", "k"), ("Mi", "m"), ("Gi", "g"), ("Ti", "t")):
        if text.endswith(iec):
            return text[:-len(iec)] + compose
    return text.lower()


def generate_docker_compose(onto, world, platform):
    services, networks, volumes = {}, set(), set()

    for unit in g.deployment_units(platform):
        service = {}

        image = g.image_reference(onto, unit)
        if image:
            service["image"] = image

        # Compose forbids a fixed container_name on a scaled-out service, so the
        # name is used only as the service key once replicas > 1.
        container_name = g.one(unit, "container_name")
        unit_replicas = g.one(unit, "replicas")
        if container_name and (unit_replicas is None or int(unit_replicas) == 1):
            service["container_name"] = container_name

        restart_policy = g.one(unit, "restart_policy")
        if restart_policy:
            service["restart"] = restart_policy

        environment = g.environment(onto, unit)
        if environment:
            service["environment"] = environment

        unit_networks = g.network_names(onto, world, unit)
        if unit_networks:
            service["networks"] = unit_networks
            networks.update(unit_networks)

        # The ephemeral/persistent classification in the ontology decides which
        # Compose construct is emitted: a named volume or a tmpfs mount.
        mounts, tmpfs = [], []
        for storage, mount_path in g.volume_mounts(onto, unit):
            if not mount_path:
                continue
            if g.is_a(storage, onto.ephemeral):
                tmpfs.append(mount_path)
                continue
            volume_name = g.one(storage, "volume_name")
            if volume_name:
                mounts.append("%s:%s" % (volume_name, mount_path))
                volumes.add(volume_name)
        if mounts:
            service["volumes"] = mounts
        if tmpfs:
            service["tmpfs"] = sorted(tmpfs)

        limits = {}
        if g.one(unit, "cpu_limit"):
            limits["cpus"] = _compose_cpus(g.one(unit, "cpu_limit"))
        if g.one(unit, "memory_limit"):
            limits["memory"] = _compose_memory(g.one(unit, "memory_limit"))
        if limits or (unit_replicas is not None and int(unit_replicas) != 1):
            deploy = {}
            if unit_replicas is not None:
                deploy["replicas"] = int(unit_replicas)
            if limits:
                deploy["resources"] = {"limits": limits}
            service["deploy"] = deploy

        ports = g.many(unit, "ports")
        if ports:
            service["ports"] = sorted(str(p) for p in ports)

        dependencies = g.depends_on_names(onto, unit)
        if dependencies:
            service["depends_on"] = dependencies

        service_name = container_name or unit.name.lower()
        services[service_name] = service

    compose = {"version": COMPOSE_VERSION,
               "services": {k: services[k] for k in sorted(services)}}
    if networks:
        compose["networks"] = {name: {} for name in sorted(networks)}
    if volumes:
        compose["volumes"] = {name: {} for name in sorted(volumes)}
    return compose


def describe(onto, world, platform):
    """Human-readable trace of what was read from the ontology."""
    print("\nPlatform '%s' (artifact_format=%s)" % (platform.name, g.one(platform, "artifact_format")))
    for unit in g.deployment_units(platform):
        print("  deployment unit: %s" % unit.name)
        print("     image           : %s" % g.image_reference(onto, unit))
        print("     networks        : %s" % g.network_names(onto, world, unit))
        print("     env             : %s" % g.environment(onto, unit))
        print("     volume mounts   : %s" % [(s.name, p) for s, p in g.volume_mounts(onto, unit)])
