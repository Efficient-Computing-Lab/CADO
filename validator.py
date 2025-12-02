import argparse
from owlready2 import *
from owlready2 import OwlReadyInconsistentOntologyError

# ------------------------------------------------------------
# 0. Parse command-line arguments
# ------------------------------------------------------------

parser = argparse.ArgumentParser(description="OWL Ontology Validator")
parser.add_argument("--classes", required=True, help="Path to the class (TBox) OWL file")
parser.add_argument("--instances", required=True, help="Path to the instance (ABox) OWL file")
args = parser.parse_args()

CLASS_FILE = args.classes
INSTANCE_FILE = args.instances

# ------------------------------------------------------------
# 1. Load schema (TBox) and instances (ABox)
# ------------------------------------------------------------

print("Loading Classes...")
onto = get_ontology(CLASS_FILE).load()

print("Loading Instances...")
instances = get_ontology(INSTANCE_FILE).load()
onto.imported_ontologies.append(instances)

print("\nLoaded ontologies:")
print(" Classes:", onto.base_iri)
print(" Instances:", instances.base_iri)

# ------------------------------------------------------------
# 2. Run reasoner (consistency & classification)
# ------------------------------------------------------------

print("\nRunning reasoner...")
try:
    with onto:
        sync_reasoner()
    print("Reasoning completed. Ontology is consistent.\n")
except OwlReadyInconsistentOntologyError as e:
    print("❌ Ontology is inconsistent!")
    print(e)
    exit()

# ------------------------------------------------------------
# 3. Check for inconsistent individuals (owl:Nothing)
# ------------------------------------------------------------

print("Checking for inconsistent individuals...")

inconsistent_individuals = list(Nothing.instances())

if inconsistent_individuals:
    print("\n❌ Inconsistent individuals detected:")
    for ind in inconsistent_individuals:
        print("  -", ind)
else:
    print("No inconsistent individuals found.\n")

# ------------------------------------------------------------
# 4. Validate individuals against class restrictions
# ------------------------------------------------------------

def check_restriction(ind, restriction):
    """Evaluate an OWL restriction for a given individual."""
    try:
        return restriction(ind)
    except Exception:
        return False

print("Validating against class restrictions...\n")

for cls in onto.classes():
    for ind in cls.instances():
        for restriction in cls.is_a:
            if isinstance(restriction, Restriction):
                if not check_restriction(ind, restriction):
                    print(f"❌ {ind} violates restriction {restriction} in class {cls}")

# ------------------------------------------------------------
# 5. Validate datatype properties
# ------------------------------------------------------------

print("\nValidating datatype property ranges...\n")

for prop in onto.data_properties():
    expected_ranges = prop.range

    # Case 1: property has declared domain
    owners = list(prop.domain)

    if owners:
        individuals_to_check = set()
        for owner in owners:
            individuals_to_check.update(owner.instances())
    else:
        # Case 2: no domain declared → scan all individuals
        individuals_to_check = set(onto.individuals())

    for ind in individuals_to_check:
        # Get values for this property on this individual
        try:
            values = getattr(ind, prop.python_name)
        except AttributeError:
            continue  # individual does not use this property

        # Validate each value
        for val in values:
            if expected_ranges:
                valid = False
                for r in expected_ranges:
                    if hasattr(r, "python_type") and isinstance(val, r.python_type):
                        valid = True
                        break

                if not valid:
                    print(f"❌ {ind}.{prop.name} = {val} violates range {expected_ranges}")

# ------------------------------------------------------------
# 6. Summary
# ------------------------------------------------------------
print("\nValidation completed.")
