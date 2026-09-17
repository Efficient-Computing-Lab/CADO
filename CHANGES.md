# CADO v2 — changes since v1

The v1 ontology and tooling are preserved in `ontology_files/v1_archive/` so that
every change below can be diffed.

Reproduce everything with `./run_evaluation.sh` (add `--live` to also deploy to a
real Docker daemon and a real Kubernetes cluster).

---

## 1. Ontology defects fixed

### 1.1 Domain and range axioms read as intersections

Multiple domain axioms on one property are conjunctive in OWL. v1 had:

| Property | v1 axioms | v1 effective meaning | v2 |
|---|---|---|---|
| `includesImage` | 3 domains | `image_registry ⊓ private ⊓ public` | domain `image_registry` |
| `pullsImageFrom` | 2 domains, 3 ranges | range `image_registry ⊓ private ⊓ public` | domain `platform ⊔ runtime_environment`, range `image_registry` |
| `unpacks` | 2 domains | `runtime_environment ⊓ platform` | domain `runtime_environment` |
| `composedOf` | **9 ranges** | filler in all nine classes at once | range `container_orchestration_environment` |
| `binds` | 2 ranges | `persistent ⊓ storage` | range `storage` |
| `reservesDiskSpaceOn` | 2 domains | `persistent ⊓ storage` | domain `storage` |

Every property in v2 has exactly one domain axiom and one range axiom; where a
union was intended it is written as an explicit `ObjectUnionOf`.

`DisjointClasses(private_image_registry, public_image_registry)` is now asserted.
Test **T3** constructs a registry including an image and confirms it is
consistent and that the registry is not silently classified as both private and
public.

### 1.2 Dependency axioms forcing existence

v1 asserted `platform ⊑ ∃composedOf.platform` together with eight further
`∃composedOf` axioms, so a single platform entailed either an infinite chain or a
composition loop. v2 removes every forced existential of this kind and replaces
it with a universal restriction: `platform ⊑ ∀composedOf.container_orchestration_environment`.
Nothing is now forced to exist. Test **T6** asserts that no existential
`composedOf` restriction remains in the T-Box.

`composedOf` and `utilizes` are additionally declared **asymmetric** and
**irreflexive**, so composition and utilisation loops are rejected rather than
merely undesirable. Tests **T4** and **T5** confirm that `p composedOf p` and
`a utilizes b utilizes a` both make the ontology inconsistent.

Only two existential axioms survive, both definitional rather than structural:
`minimal_deployment_unit ⊑ =1 runningInstanceOf.image` and
`persistent ⊑ ≥1 reservesDiskSpaceOn.host`.

### 1.3 Naming

`hosts` → `host` and `secrets` → `secret`. The name `hosts` is reused for the
object property that is the inverse of `hostedBy`, where a plural verb form is
correct.

### 1.4 Namespace

v1 used two IRI schemes in the same file. `IRI="group_by"` resolved to
`…/2024/group_by` while `IRI="#deployment_unit"` resolved to
`…/2024/#deployment_unit`. Six classes and three object properties
(`#binds`, `#deploys`, `#hostedBy`) were therefore in a different namespace from
the rest of the ontology. v2 uses one namespace throughout.

### 1.5 Documentation

v1 contained **zero** `rdfs:label` and `rdfs:comment` annotations, and zero
`DataPropertyDomain` / `DataPropertyRange` axioms. In v2 every one of the 70
terms carries a label and a natural-language definition, and every data property
has a declared domain and an XSD range. The ontology also declares a version IRI,
title, creator and licence. The validator fails the build if any term is
undocumented.

---

## 2. The ontology is no longer example-specific

v1 declared six data properties in the **T-Box** that were specific to the
running example: `env_mysql_database`, `env_mysql_root_password`,
`env_wordpress_db_host`, `env_wordpress_db_name`, `env_wordpress_db_password`,
`env_wordpress_db_user`. No deployment other than WordPress + MySQL could be
described without extending the schema.

v2 reifies environment variables as a class with `variable_name` and
`variable_value`. Further string properties that encoded references to other
individuals are replaced by object properties or removed as redundant:

| v1 string property | v2 replacement |
|---|---|
| `related_image` | `runningInstanceOf` → `image_name` |
| `related_namespace` | inverse of `includesRunningInstance` → `namespace_name` |
| `networks` | inverse of `includesRunningInstance` → `network_name` |
| `related_volume`, `volumes` | `hasVolumeMount` → `mountsStorage` (reified `volume_mount`) |
| `depends_on` | `dependsOn` object property |

Volume mounts are reified so a unit may mount several volumes unambiguously,
which the `"name:/path"` string of v1 could not express.

Test **T8** demonstrates a three-tier microservice deployment expressed with an
**unchanged** T-Box.

---

## 3. The converter is driven by the ontology

In v1 the converter selected individuals by substring matching on their *names*
(`"Pod" in inst.name`, `"Docker_Container" in inst.name`) and linked pods to
volumes by a shared name prefix. It read only data properties, so the ontology's
relational structure played no part in the transformation.

v2 introduces `cado_graph.py`, which expresses every lookup as a traversal of the
ontology. The converter selects a backend from the `artifact_format` property
declared on each platform individual, not from its name.

Test **T7** renames ten individuals (`MySQL_Pod` → `Alpha_Workload` and so on)
and confirms the generated artifacts are **byte-identical**. Under v1 the same
rename produces empty output.

Test **T12** confirms the transformation consumes reasoner-derived facts, not
only asserted ones.

The converter's remaining role is platform-specific translation the ontology
deliberately does not encode. Test **T11** covers the clearest case — a CPU limit
recorded once as `500m` becomes `0.5` in Compose and stays `500m` in Kubernetes,
and `512Mi` becomes `512m` in Compose. Test **T9** shows the ontology's
`ephemeral` / `persistent` distinction driving different artifacts: `tmpfs`
versus a named volume in Compose, `emptyDir` versus a PersistentVolumeClaim in
Kubernetes. v1 ignored the distinction entirely and never instantiated the
`ephemeral` class.

---

## 4. Competency questions and reasoning

`competency_questions.py` states 13 competency questions with the SPARQL query
that answers each. Three require the reasoner and are marked `[INFERRED]`; four
are defect checks where a non-empty answer indicates a modelling error.

Two **defined classes** make the axiomatisation do work rather than merely exist:

- `subplatform ≡ platform ⊓ ∃utilizedBy.platform` — inferred, not asserted. The
  reasoner classifies `Docker` and `Docker_Compose` as subplatforms and correctly
  does not classify `Kubernetes` as one.
- `stateful_deployment_unit ≡ deployment_unit ⊓ ∃hasVolumeMount.(∃mountsStorage.persistent)`

A **property chain** `hasVolumeMount ∘ mountsStorage ⊑ binds` derives the binding
between a unit and its storage instead of requiring it to be asserted twice.

`validator.py` performs two distinct checks: HermiT for open-world consistency,
and closed-world constraint checking, because an OWL domain axiom is an
inference rule rather than a constraint — asserting `image1 includesImage image2`
does not raise an error in OWL, it silently infers that `image1` is a registry.

`ontology_summary.py` emits a compact summary of all classes, object properties,
data properties, domains, ranges and restrictions, in Markdown
(`ONTOLOGY_SUMMARY.md`) or LaTeX.

---

## 5. Evaluation on real platforms

The generated artifacts are executed on real platforms, and
`run_evaluation.sh --live` reproduces this.

**Docker.** `docker compose config` accepts both generated Compose files. The
WordPress example was deployed with `docker compose up`; both containers reached
`running`, WordPress connected to MySQL over the ontology-declared environment
variables, and the volume was mounted at the declared path.

*This exposed two real defects in the generated output*, now fixed: Compose
rejects Kubernetes-style `500m` CPU and `512Mi` memory limits, so the converter
translates them.

**Kubernetes.** A single-node cluster was created with `kind` (v1.29.2). All
seven WordPress manifests were accepted; both Deployments reached `1/1 Ready` and
both PersistentVolumeClaims reached `Bound`. A file written inside the WordPress
pod appeared on the node at `/mnt/data/wordpress`, the exact hostPath the
ontology declares.

The microservice manifests were also applied: `edge-deployment` reached `3/3`
replicas as declared, `cache-deployment` reached `1/1`, the PVC bound at 10Gi,
resource limits arrived intact, and the ephemeral cache volume was created as an
`emptyDir` with no PVC. The two `api-deployment` pods remain in `ErrImagePull`
because that example deliberately references a fictional private registry
(`registry.example.com`); this is expected and is what exercises the
`private_image_registry` and `secret` part of the ontology.

`artifact_check.py` additionally validates the artifacts offline — required keys,
cross-references between resources, and that every volumeMount names a volume the
pod declares — since `kubectl --dry-run=client` needs a reachable API server.

---

## 6. Figures

All ontology figures are now generated from `entity.owx` and the A-Box files by
`ontology_python_tools/generate_figures.py`. A figure can therefore no longer
disagree with the axioms it illustrates.

The previous Protege OntoGraf exports were unusable at page width because of
their aspect ratio, not their font size: the Kubernetes use case was 72.7 inches
wide at natural size, so its labels rendered at 2.1 pt once scaled to a 6.9 inch
text width. Every figure now renders its labels at 6.9 pt or larger, and most at
10 pt or more.

| Change | Effect |
|---|---|
| Generated from the OWL source | a figure cannot name a property the ontology lacks |
| Laid out close to page-shaped, use cases split into stack and application views | 2.1 pt -> 6.9-25 pt at text width |
| Property names written on the edges | no colour-to-legend tracing |
| Opaque label backgrounds | edges pass behind labels instead of through the text |
| One colour per relationship, consistent across figures | minimum separation of 36 CIE Lab units within any figure |
| Published as editable `.drawio` alongside each PDF | figures can be adjusted without redrawing them |

The generator records a checksum of everything it writes. A figure that is
edited by hand is detected on the next run, reported, and left alone rather than
overwritten; `--force` regenerates it and discards the edits.

---

## Known limitations

- The ontology IRI is still the Protege-style default
  `http://www.semanticweb.org/container-ontologies/2024/`. A persistent IRI
  (w3id.org or purl.org) would be better practice.
- No user study has been run, so nothing here supports a claim about ease of use
  or learning curve.
