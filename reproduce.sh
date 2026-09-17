#!/usr/bin/env bash
#
# CADO reproduction script.
#
# Reproduces the artifact results reported in the Evaluation section:
#
#   1. validation of both models with the HermiT reasoner,
#   2. generation of the Docker Compose and Kubernetes artifacts for both models,
#   3. an offline structural check of the generated artifacts.
#
# With --live it additionally deploys the generated artifacts to a Docker daemon
# and to a Kubernetes cluster created with kind, then tears both down.
#
#   ./reproduce.sh           # offline; needs python3 and java
#   ./reproduce.sh --live    # also needs docker and kind
#
# For the competency questions, the regression tests, the summary tables and the
# figures, see run_evaluation.sh, which runs everything.
#
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLS="$ROOT/ontology_python_tools"
ONTO="$ROOT/ontology_files"
TBOX="$ONTO/entity.owx"
OUT="$ROOT/generated_files"
MICRO="$OUT/microservice"

COMPOSE_PROJECT="cadorepro"
KIND_CLUSTER="cado-repro"
K8S_NAMESPACE="wordpress-namespace"

LIVE=0
case "${1:-}" in
    --live) LIVE=1 ;;
    -h|--help) sed -n '2,19p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    "") ;;
    *) printf 'Unknown option: %s (try --help)\n' "$1" >&2; exit 2 ;;
esac

FAILURES=0
step()  { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
check() {
    if [ "$1" -eq 0 ]; then printf '    OK\n'
    else printf '    FAILED (exit %s)\n' "$1"; FAILURES=$((FAILURES + 1)); fi
}
need() {
    command -v "$1" >/dev/null 2>&1 && return 0
    printf '    %s not found; --live requires it.\n' "$1" >&2
    return 1
}

cd "$TOOLS" || exit 1

# ------------------------------------------------- 1. validation of the models
for abox in instances.owl instances_microservice.owl; do
    step "Validating $abox (HermiT consistency + closed-world constraints)"
    python3 validator.py --classes "$TBOX" --instances "$ONTO/$abox" | tail -4
    check "${PIPESTATUS[0]}"
done

# ------------------------------------------------------ 2. artifact generation
step "Generating deployment artifacts: WordPress + MySQL"
python3 converter.py --classes "$TBOX" --instances "$ONTO/instances.owl" \
        --out "$OUT" | tail -3
check "${PIPESTATUS[0]}"

step "Generating deployment artifacts: three-tier microservice"
python3 converter.py --classes "$TBOX" --instances "$ONTO/instances_microservice.owl" \
        --out "$MICRO" | tail -3
check "${PIPESTATUS[0]}"

# ------------------------------------------------ 3. offline structural check
step "Structural validation of the generated artifacts"
python3 "$TOOLS/artifact_check.py" "$OUT" "$MICRO" | tail -2
check "${PIPESTATUS[0]}"

# ----------------------------------------------------- 4. optional deployment
teardown() {
    docker compose -f "$OUT/docker-compose.generated.yml" \
        -p "$COMPOSE_PROJECT" down -v >/dev/null 2>&1
    kind delete cluster --name "$KIND_CLUSTER" >/dev/null 2>&1
}

if [ "$LIVE" -eq 1 ]; then
    if ! need docker || ! need kind || ! need kubectl; then
        FAILURES=$((FAILURES + 1))
    else
        # Tear both environments down on any exit path, including Ctrl-C, so a
        # failed run never leaves a cluster or a volume behind.
        trap teardown EXIT INT TERM

        step "LIVE: deploying the generated Compose file to Docker"
        docker compose -f "$OUT/docker-compose.generated.yml" \
            -p "$COMPOSE_PROJECT" up -d >/dev/null 2>&1
        check $?
        waited=0
        until docker exec mysql mysqladmin ping -uroot -pexample_password --silent >/dev/null 2>&1; do
            sleep 3; waited=$((waited + 3))
            if [ "$waited" -ge 180 ]; then
                printf '    MySQL did not become ready within 180s\n'
                FAILURES=$((FAILURES + 1)); break
            fi
        done
        docker compose -p "$COMPOSE_PROJECT" ps
        docker compose -f "$OUT/docker-compose.generated.yml" \
            -p "$COMPOSE_PROJECT" down -v >/dev/null 2>&1

        step "LIVE: deploying the generated manifests to a kind cluster"
        kind create cluster --name "$KIND_CLUSTER" --wait 180s >/dev/null 2>&1
        check $?
        kubectl apply -f "$OUT/kubernetes-namespace.generated.yml" >/dev/null
        for kind_of in volume pvc deployment; do
            for manifest in "$OUT"/kubernetes-${kind_of}*.yml; do
                [ -e "$manifest" ] || continue
                kubectl apply -f "$manifest" >/dev/null
            done
        done
        waited=0
        until [ "$(kubectl get deploy -n "$K8S_NAMESPACE" \
                  -o jsonpath='{.items[*].status.readyReplicas}' 2>/dev/null)" = "1 1" ]; do
            sleep 5; waited=$((waited + 5))
            if [ "$waited" -ge 300 ]; then
                printf '    Deployments did not become ready within 300s\n'
                FAILURES=$((FAILURES + 1)); break
            fi
        done
        kubectl get deploy,pvc,pods -n "$K8S_NAMESPACE"
        kind delete cluster --name "$KIND_CLUSTER" >/dev/null 2>&1

        trap - EXIT INT TERM
    fi
fi

printf '\n%s\n' "------------------------------------------------------------"
if [ "$FAILURES" -eq 0 ]; then
    printf 'Reproduction completed: all steps passed.\n'
else
    printf 'Reproduction completed: %d step(s) failed.\n' "$FAILURES"
fi
exit "$FAILURES"
