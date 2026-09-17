"""
Competency questions for CADO.

Each question states an information need the ontology is meant to answer,
together with the SPARQL query that answers it. Questions marked [INFERRED]
cannot be answered from the asserted axioms alone: they require the reasoner,
and therefore demonstrate that the axiomatisation does work rather than merely
being present.

Usage:
    python competency_questions.py --classes ../ontology_files/entity.owx \
                                   --instances ../ontology_files/instances.owl
"""

import argparse
import os

from owlready2 import get_ontology, default_world, onto_path, sync_reasoner

PREFIX = """PREFIX : <http://www.semanticweb.org/container-ontologies/2024/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
"""

QUESTIONS = [
 ("CQ1", "Which platforms can emit deployment artifacts, and in which format?", """
    SELECT ?platform ?format WHERE {
        ?platform a :platform ; :artifact_format ?format .
    } ORDER BY ?platform"""),

 ("CQ2", "Which deployment units does each platform manage?", """
    SELECT ?platform ?unit WHERE {
        ?platform a :platform ; :deploys ?unit .
    } ORDER BY ?platform ?unit"""),

 ("CQ3", "Which images must be retrievable for the described deployment?", """
    SELECT DISTINCT ?image_name WHERE {
        ?unit :runningInstanceOf ?image . ?image :image_name ?image_name .
    } ORDER BY ?image_name"""),

 ("CQ4", "[INFERRED] Which deployment units are stateful, i.e. mount persistent storage?", """
    SELECT ?unit WHERE {
        ?unit a :stateful_deployment_unit .
    } ORDER BY ?unit"""),

 ("CQ5", "[INFERRED] Which platforms operate as a component of another platform?", """
    SELECT ?sub ?parent WHERE {
        ?sub a :subplatform . ?parent :utilizes ?sub . ?parent a :platform .
    } ORDER BY ?sub"""),

 ("CQ6", "[INFERRED] Which storage does each unit bind? (derived by property chain)", """
    SELECT ?unit ?volume_name WHERE {
        ?unit :binds ?storage . ?storage :volume_name ?volume_name .
    } ORDER BY ?unit"""),

 ("CQ7", "Which hosts must supply backing disk space for the deployment?", """
    SELECT DISTINCT ?host WHERE {
        ?storage a :persistent ; :reservesDiskSpaceOn ?host .
    } ORDER BY ?host"""),

 ("CQ8", "Which grouping construct scopes each deployment unit, and of what kind?", """
    SELECT ?group ?kind ?unit WHERE {
        ?group :includesRunningInstance ?unit ; a ?kind .
        FILTER(?kind IN (:network, :namespace, :service))
    } ORDER BY ?unit ?group"""),

 ("CQ9", "Do the two target platforms agree on the environment of the same service?", """
    SELECT ?variable ?value (COUNT(DISTINCT ?unit) AS ?units) WHERE {
        ?unit :hasEnvironmentVariable ?env .
        ?env :variable_name ?variable ; :variable_value ?value .
    } GROUP BY ?variable ?value ORDER BY ?variable"""),

 # -- The following are validation queries: a non-empty result is a defect. --
 ("CQ10", "DEFECT CHECK: persistent storage declared but mounted by nothing.", """
    SELECT ?storage WHERE {
        ?storage a :persistent .
        FILTER NOT EXISTS { ?mount :mountsStorage ?storage }
    } ORDER BY ?storage"""),

 ("CQ11", "DEFECT CHECK: deployment units with no image to run.", """
    SELECT ?unit WHERE {
        ?unit a :deployment_unit .
        FILTER NOT EXISTS { ?unit :runningInstanceOf ?image }
    } ORDER BY ?unit"""),

 ("CQ12", "DEFECT CHECK: a unit depending on one that no common platform deploys.", """
    SELECT ?unit ?dependency WHERE {
        ?unit :dependsOn ?dependency .
        FILTER NOT EXISTS {
            ?platform :deploys ?unit ; :deploys ?dependency .
        }
    } ORDER BY ?unit"""),

 ("CQ13", "DEFECT CHECK: private registries reachable without a secret.", """
    SELECT ?registry WHERE {
        ?registry a :private_image_registry .
        FILTER NOT EXISTS { ?secret :loginTo ?registry }
    } ORDER BY ?registry"""),
]


def shorten(value):
    if hasattr(value, "name"):
        return value.name
    return str(value)


def main():
    parser = argparse.ArgumentParser(description="Run the CADO competency questions")
    parser.add_argument("--classes", required=True)
    parser.add_argument("--instances", required=True)
    parser.add_argument("--no-reasoner", action="store_true")
    args = parser.parse_args()

    onto_path.append(os.path.dirname(os.path.abspath(args.classes)))
    get_ontology(os.path.abspath(args.classes)).load()
    abox = get_ontology(os.path.abspath(args.instances)).load()
    if not args.no_reasoner:
        with abox:
            sync_reasoner(infer_property_values=True, debug=0)

    defects = 0
    for identifier, question, query in QUESTIONS:
        rows = list(default_world.sparql(PREFIX + query))
        print("\n%s  %s" % (identifier, question))
        if not rows:
            if "DEFECT CHECK" in question:
                print("     PASS - no violations")
            else:
                print("     (no results)")
            continue
        if "DEFECT CHECK" in question:
            defects += len(rows)
            print("     FAIL - %d violation(s)" % len(rows))
        for row in rows:
            print("     " + " | ".join(shorten(cell) for cell in row))

    print("\n%s" % ("-" * 60))
    print("Competency questions answered: %d" % len(QUESTIONS))
    print("Defect checks failing:        %d" % defects)


if __name__ == "__main__":
    main()
