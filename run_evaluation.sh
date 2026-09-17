#!/usr/bin/env bash
#
# CADO reproducibility script.
#
# Reproduces every result reported for CADO, in order. Without arguments it runs
# the offline evaluation (validation, competency questions, regression tests,
# artifact generation and static artifact validation). With --live it also
# deploys the generated artifacts to a real Docker daemon and a real Kubernetes
# cluster created with kind, then tears both down.
#
#   ./run_evaluation.sh            # offline; needs python3 + java
#   ./run_evaluation.sh --live     # also needs docker and kind
#
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLS="$ROOT/ontology_python_tools"
ONTO="$ROOT/ontology_files"
TBOX="$ONTO/entity.owx"
LIVE=0
[ "${1:-}" = "--live" ] && LIVE=1

FAILURES=0
step() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
check() {
    if [ "$1" -eq 0 ]; then printf '    OK\n'
    else printf '    FAILED (exit %s)\n' "$1"; FAILURES=$((FAILURES + 1)); fi
}

cd "$TOOLS" || exit 1

# ---------------------------------------------------------------- 1. ontology
for abox in instances.owl instances_microservice.owl; do
    step "Validating $abox (HermiT consistency + closed-world constraints)"
    python3 validator.py --classes "$TBOX" --instances "$ONTO/$abox" | tail -4
    check "${PIPESTATUS[0]}"
done

step "Answering the competency questions"
python3 competency_questions.py --classes "$TBOX" --instances "$ONTO/instances.owl" | tail -4
check "${PIPESTATUS[0]}"

step "Running the regression and evidence tests"
python3 regression_tests.py | tail -3
check "${PIPESTATUS[0]}"

step "Regenerating the ontology summary tables"
python3 ontology_summary.py --classes "$TBOX" --out "$ROOT/ONTOLOGY_SUMMARY.md"
check $?

step "Regenerating the figures from the ontology"
python3 generate_figures.py --ontology "$ONTO" --out "$ROOT/figures" | tail -3
check "${PIPESTATUS[0]}"

# --------------------------------------------------------------- 2. artifacts
step "Generating deployment artifacts: WordPress + MySQL"
python3 converter.py --classes "$TBOX" --instances "$ONTO/instances.owl" \
        --out "$ROOT/generated_files" | tail -3
check "${PIPESTATUS[0]}"

step "Generating deployment artifacts: three-tier microservice"
python3 converter.py --classes "$TBOX" --instances "$ONTO/instances_microservice.owl" \
        --out "$ROOT/generated_files/microservice" | tail -3
check "${PIPESTATUS[0]}"

# ------------------------------------------------- 3. static artifact validation
if command -v docker >/dev/null 2>&1; then
    for dir in "$ROOT/generated_files" "$ROOT/generated_files/microservice"; do
        step "docker compose config: $(basename "$dir")"
        docker compose -f "$dir/docker-compose.generated.yml" config >/dev/null 2>&1
        check $?
    done
else
    printf '\n    docker not found; skipping Compose validation\n'
fi

step "Structural validation of the generated artifacts"
python3 "$TOOLS/artifact_check.py" "$ROOT/generated_files" "$ROOT/generated_files/microservice" | tail -2
check "${PIPESTATUS[0]}"

if command -v kubectl >/dev/null 2>&1 && kubectl cluster-info >/dev/null 2>&1; then
    # kubectl needs a reachable API server even for a client-side dry run, so
    # this step only runs when a cluster is available. Use --live to create one.
    for dir in "$ROOT/generated_files" "$ROOT/generated_files/microservice"; do
        step "kubectl dry-run against the live API server: $(basename "$dir")"
        ok=0
        for manifest in "$dir"/kubernetes-*.yml; do
            kubectl apply --dry-run=client -f "$manifest" >/dev/null 2>&1 || ok=1
        done
        check "$ok"
    done
else
    printf '\n    No Kubernetes cluster reachable; manifests checked structurally only.\n'
    printf '    Run with --live to validate them against a real API server.\n'
fi

# ----------------------------------------------------------- 4. live deployment
if [ "$LIVE" -eq 1 ]; then
    step "LIVE: deploying the generated Compose file to Docker"
    docker compose -f "$ROOT/generated_files/docker-compose.generated.yml" \
        -p cadoeval up -d >/dev/null 2>&1
    check $?
    until docker exec mysql mysqladmin ping -uroot -pexample_password --silent >/dev/null 2>&1; do
        sleep 3
    done
    docker compose -p cadoeval ps
    docker compose -f "$ROOT/generated_files/docker-compose.generated.yml" \
        -p cadoeval down -v >/dev/null 2>&1

    step "LIVE: deploying the generated manifests to a kind cluster"
    kind create cluster --name cado-eval --wait 180s >/dev/null 2>&1
    check $?
    kubectl apply -f "$ROOT/generated_files/kubernetes-namespace.generated.yml" >/dev/null
    for kind_of in volume pvc deployment; do
        for manifest in "$ROOT"/generated_files/kubernetes-${kind_of}*.yml; do
            kubectl apply -f "$manifest" >/dev/null
        done
    done
    until [ "$(kubectl get deploy -n wordpress-namespace \
              -o jsonpath='{.items[*].status.readyReplicas}' 2>/dev/null)" = "1 1" ]; do
        sleep 5
    done
    kubectl get deploy,pvc,pods -n wordpress-namespace
    kind delete cluster --name cado-eval >/dev/null 2>&1
fi

printf '\n%s\n' "------------------------------------------------------------"
if [ "$FAILURES" -eq 0 ]; then
    printf 'Evaluation completed: all steps passed.\n'
else
    printf 'Evaluation completed: %d step(s) failed.\n' "$FAILURES"
fi
exit "$FAILURES"
