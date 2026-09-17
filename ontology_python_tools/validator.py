"""
CADO validator.

Two complementary checks are performed.

1. Open-world reasoning (HermiT): is the ontology consistent, are all classes
   satisfiable, and does any individual end up in owl:Nothing?

2. Closed-world constraint checking: under OWL semantics a domain or range
   axiom is an *inference rule*, not a constraint -- asserting
   `image1 includesImage image2` does not raise an error, it silently infers
   that image1 is an image_registry. A modelling mistake therefore stays
   invisible to the reasoner. The checks below re-read the same axioms as
   integrity constraints over the asserted A-Box, which is what a deployment
   engineer actually wants to be told about.

Usage:
    python validator.py --classes ../ontology_files/entity.owx \
                        --instances ../ontology_files/instances.owl
"""

import argparse
import os
import sys

from owlready2 import (get_ontology, default_world, onto_path, sync_reasoner,
                       Thing, Nothing, OwlReadyInconsistentOntologyError,
                       ObjectPropertyClass, DataPropertyClass, Or, FunctionalProperty)


class Report:
    def __init__(self):
        self.errors = []
        self.warnings = []

    def error(self, message):
        self.errors.append(message)

    def warn(self, message):
        self.warnings.append(message)

    def section(self, title, items, label="OK"):
        print("\n%s" % title)
        if not items:
            print("   %s" % label)
        for item in items:
            print("   - %s" % item)


def class_expression_members(expression):
    """Flatten a class expression into the list of named classes it permits."""
    if isinstance(expression, Or):
        members = []
        for part in expression.Classes:
            members.extend(class_expression_members(part))
        return members
    return [expression]


def satisfies(individual, expression):
    return any(isinstance(individual, cls) for cls in class_expression_members(expression))


def check_domains_and_ranges(tbox, world, report):
    """Domain and range axioms enforced as constraints rather than inferences."""
    for prop in list(tbox.object_properties()) + list(tbox.data_properties()):
        is_object = isinstance(prop, ObjectPropertyClass)
        for subject in world.individuals():
            values = getattr(subject, prop.python_name, None)
            if values is None:
                continue
            values = values if isinstance(values, list) else [values]
            if not values:
                continue

            for domain in prop.domain or []:
                if not satisfies(subject, domain):
                    report.error("domain violation: %s uses %s but is not a %s"
                                 % (subject.name, prop.name, domain))

            if not is_object:
                continue
            for value in values:
                for range_expression in prop.range or []:
                    if not satisfies(value, range_expression):
                        report.error("range violation: %s %s %s, but %s is not a %s"
                                     % (subject.name, prop.name, value.name,
                                        value.name, range_expression))


def check_data_types(tbox, world, report):
    for prop in tbox.data_properties():
        expected = [r for r in (prop.range or []) if isinstance(r, type)]
        if not expected:
            continue
        for subject in world.individuals():
            values = getattr(subject, prop.python_name, None)
            if values is None:
                continue
            values = values if isinstance(values, list) else [values]
            for value in values:
                if not any(isinstance(value, python_type) for python_type in expected):
                    report.error("datatype violation: %s.%s = %r (%s), expected %s"
                                 % (subject.name, prop.name, value,
                                    type(value).__name__,
                                    "/".join(t.__name__ for t in expected)))


def check_functionality(tbox, world, report):
    for prop in tbox.data_properties():
        if FunctionalProperty not in prop.is_a:
            continue
        for subject in world.individuals():
            values = getattr(subject, prop.python_name, None)
            if isinstance(values, list) and len(values) > 1:
                report.error("functionality violation: %s.%s has %d values %r"
                             % (subject.name, prop.name, len(values), values))


def check_disjointness(tbox, world, report):
    for axiom in tbox.disjoint_classes():
        classes = list(axiom.entities)
        for subject in world.individuals():
            matched = [c for c in classes if isinstance(subject, c)]
            if len(matched) > 1:
                report.error("disjointness violation: %s belongs to %s"
                             % (subject.name, " and ".join(c.name for c in matched)))


def check_documentation(tbox, report):
    """Every term should carry a label and a definition."""
    entities = (list(tbox.classes()) + list(tbox.object_properties())
                + list(tbox.data_properties()))
    for entity in entities:
        if not entity.label:
            report.warn("%s has no rdfs:label" % entity.name)
        if not entity.comment:
            report.warn("%s has no rdfs:comment (definition)" % entity.name)


def main():
    parser = argparse.ArgumentParser(description="CADO ontology validator")
    parser.add_argument("--classes", required=True, help="Path to the T-Box OWL file")
    parser.add_argument("--instances", required=True, help="Path to the A-Box OWL file")
    args = parser.parse_args()

    onto_path.append(os.path.dirname(os.path.abspath(args.classes)))
    print("Loading T-Box ...")
    tbox = get_ontology(os.path.abspath(args.classes)).load()
    print("Loading A-Box ...")
    abox = get_ontology(os.path.abspath(args.instances)).load()

    print("\n%s\n1. OPEN-WORLD REASONING (HermiT)\n%s" % ("=" * 60, "=" * 60))
    print("   T-Box: %d classes, %d object properties, %d data properties"
          % (len(list(tbox.classes())), len(list(tbox.object_properties())),
             len(list(tbox.data_properties()))))
    print("   A-Box: %d individuals" % len(list(abox.individuals())))

    try:
        with abox:
            sync_reasoner(infer_property_values=True, debug=0)
        print("   Consistency: CONSISTENT")
    except OwlReadyInconsistentOntologyError as exc:
        print("   Consistency: INCONSISTENT\n   %s" % exc)
        sys.exit(1)

    unsatisfiable = [c.name for c in tbox.classes() if Nothing in c.equivalent_to]
    print("   Unsatisfiable classes: %s" % (", ".join(unsatisfiable) or "none"))
    empty = [i.name for i in Nothing.instances()]
    print("   Individuals in owl:Nothing: %s" % (", ".join(empty) or "none"))
    if unsatisfiable or empty:
        sys.exit(1)

    print("\n%s\n2. CLOSED-WORLD CONSTRAINT CHECKING\n%s" % ("=" * 60, "=" * 60))
    report = Report()
    check_domains_and_ranges(tbox, default_world, report)
    check_data_types(tbox, default_world, report)
    check_functionality(tbox, default_world, report)
    check_disjointness(tbox, default_world, report)
    check_documentation(tbox, report)

    report.section("Constraint violations:", report.errors, label="none")
    report.section("Documentation warnings:", report.warnings, label="none")

    print("\n%s" % ("-" * 60))
    print("Validation completed: %d error(s), %d warning(s)"
          % (len(report.errors), len(report.warnings)))
    sys.exit(1 if report.errors else 0)


if __name__ == "__main__":
    main()
