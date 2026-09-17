"""
Ontology access layer for CADO.

Every lookup in this module is expressed as a traversal of the CADO ontology:
individuals are selected by class membership and navigated through object
properties. No function inspects the *name* of an individual to decide what it
is. This is what makes the transformation ontology-driven rather than
convention-driven -- renaming any individual leaves the generated artifacts
unchanged.
"""


def one(individual, prop_name, default=None):
    """Read a property that may be functional (scalar) or not (list)."""
    value = getattr(individual, prop_name, None)
    if value is None:
        return default
    if isinstance(value, list):
        return value[0] if value else default
    return value


def many(individual, prop_name):
    """Read a property as a list, whether or not it is functional."""
    value = getattr(individual, prop_name, None)
    if value is None:
        return []
    return list(value) if isinstance(value, list) else [value]


def inverse(world, individual, prop_name):
    """Subjects s such that s prop_name individual, without relying on
    materialised inverse properties."""
    found = []
    for candidate in world.individuals():
        if individual in many(candidate, prop_name):
            found.append(candidate)
    return found


def is_a(individual, cls):
    """Class membership, including inferred and subclass membership."""
    return isinstance(individual, cls)


# ----------------------------------------------------------------------
# Deployment topology
# ----------------------------------------------------------------------

def target_platforms(onto, world):
    """Platforms that declare a concrete artifact format.

    The converter dispatches on the artifact_format data property rather than
    on platform names, so adding a new backend requires no change here.
    """
    platforms = []
    for individual in world.individuals():
        if is_a(individual, onto.platform) and one(individual, "artifact_format"):
            platforms.append(individual)
    return sorted(platforms, key=lambda p: p.name)


def deployment_units(platform):
    """Deployment units the platform manages: platform -deploys-> unit."""
    return sorted(many(platform, "deploys"), key=lambda u: u.name)


def image_reference(onto, unit):
    """unit -runningInstanceOf-> image -image_name-> literal.

    Replaces the v1 `related_image` string, which duplicated image_name and had
    to be kept in sync by hand.
    """
    for image in many(unit, "runningInstanceOf"):
        if is_a(image, onto.image):
            name = one(image, "image_name")
            if name:
                return name
    return None


def groups_of(onto, world, unit, group_class):
    """Grouping constructs of a given kind that scope this unit:
    group -includesRunningInstance-> unit."""
    groups = [g for g in inverse(world, unit, "includesRunningInstance")
              if is_a(g, group_class)]
    return sorted(groups, key=lambda g: g.name)


def network_names(onto, world, unit):
    """Replaces the v1 `networks` string property."""
    return [one(g, "network_name") for g in groups_of(onto, world, unit, onto.network)
            if one(g, "network_name")]


def namespace_name(onto, world, unit, default="default"):
    """Replaces the v1 `related_namespace` string property."""
    for group in groups_of(onto, world, unit, onto.namespace):
        name = one(group, "namespace_name")
        if name:
            return name
    return default


def volume_mounts(onto, unit):
    """[(storage, mount_path)] via unit -hasVolumeMount-> mount -mountsStorage-> storage.

    Replaces the v1 `volumes` string ("name:/path"), which could not express a
    unit mounting more than one volume.
    """
    mounts = []
    for mount in many(unit, "hasVolumeMount"):
        path = one(mount, "mount_path")
        for storage in many(mount, "mountsStorage"):
            mounts.append((storage, path))
    return sorted(mounts, key=lambda m: (m[0].name, m[1] or ""))


def environment(onto, unit):
    """{name: value} via unit -hasEnvironmentVariable-> variable.

    Replaces the six example-specific env_* data properties of v1, which made
    the T-Box unable to describe any deployment other than WordPress + MySQL.
    """
    env = {}
    for variable in many(unit, "hasEnvironmentVariable"):
        key, value = one(variable, "variable_name"), one(variable, "variable_value")
        if key is not None and value is not None:
            env[key] = value
    return dict(sorted(env.items()))


def depends_on_names(onto, unit):
    """Startup ordering, via the dependsOn object property."""
    names = []
    for other in many(unit, "dependsOn"):
        label = one(other, "container_name") or other.name.lower()
        names.append(label)
    return sorted(names)


def secret_label(secret):
    """Label for a secret individual.

    Follows the same pattern as container_name and deployment_name: an asserted
    name if the ontology carries one, otherwise the individual's own name
    normalised to the syntax the target platform accepts.
    """
    return one(secret, "secret_name") or secret.name.lower().replace("_", "-")


def image_pull_secrets(onto, world, unit):
    """Secrets that authenticate the pull of this unit's image.

    unit -runningInstanceOf-> image <-includesImage- registry <-loginTo- secret,
    where the registry is private. A unit whose image comes from a public
    registry yields nothing, so a credential reaches the generated artifact only
    where the ontology states that one is required.
    """
    secrets = []
    for image in many(unit, "runningInstanceOf"):
        if not is_a(image, onto.image):
            continue
        for registry in inverse(world, image, "includesImage"):
            if not is_a(registry, onto.private_image_registry):
                continue
            for secret in inverse(world, registry, "loginTo"):
                if is_a(secret, onto.secret):
                    secrets.append(secret_label(secret))
    return sorted(set(secrets))


def persistent_volumes(onto, platform):
    """Distinct persistent storage resources mounted by this platform's units."""
    seen, volumes = set(), []
    for unit in deployment_units(platform):
        for storage, _ in volume_mounts(onto, unit):
            if is_a(storage, onto.persistent) and storage.name not in seen:
                seen.add(storage.name)
                volumes.append(storage)
    return sorted(volumes, key=lambda v: one(v, "volume_name") or v.name)
