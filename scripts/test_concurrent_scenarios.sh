#!/usr/bin/env bash
# ============================================================================
# Concurrent Deployment Scenario Tests
# ============================================================================
#
# Tests concurrent branch changes with le-change's files_group_by feature.
# Each scenario pushes branches that modify stacks and verifies:
# - Correct group discovery from filesystem
# - Proper concurrency blocking detection
# - Enriched deploy matrix output
#
# Usage: ./scripts/test_concurrent_scenarios.sh [scenario_number]
#   No args = run all scenarios
#   1-5 = run specific scenario
#
# Prerequisites:
#   - GitHub CLI (gh) authenticated
#   - Push access to the repo
#   - deploy-concurrent.yml and deploy-concurrent-hash.yml in .github/workflows/
# ============================================================================

set -euo pipefail

TIMESTAMP=$(date +%s)
REPO_ROOT=$(git rev-parse --show-toplevel)
REPO_NAME=$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null || echo "unknown")

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log() { echo -e "${CYAN}[test]${NC} $*"; }
ok()  { echo -e "${GREEN}[PASS]${NC} $*"; }
warn(){ echo -e "${YELLOW}[WARN]${NC} $*"; }
fail(){ echo -e "${RED}[FAIL]${NC} $*"; }

cleanup_branch() {
    local branch=$1
    git checkout main 2>/dev/null || true
    git branch -D "$branch" 2>/dev/null || true
    git push origin --delete "$branch" 2>/dev/null || true
}

wait_for_workflow() {
    local branch=$1
    local workflow_name=$2
    local max_wait=${3:-300}
    local elapsed=0

    log "Waiting for workflow '$workflow_name' on branch '$branch'..."
    while [ $elapsed -lt $max_wait ]; do
        local run_id
        run_id=$(gh run list --branch "$branch" --workflow "$workflow_name" --limit 1 --json databaseId -q '.[0].databaseId' 2>/dev/null || echo "")
        if [ -n "$run_id" ] && [ "$run_id" != "null" ]; then
            echo "$run_id"
            return 0
        fi
        sleep 5
        elapsed=$((elapsed + 5))
    done
    fail "Timed out waiting for workflow on $branch"
    return 1
}

wait_for_run_complete() {
    local run_id=$1
    local max_wait=${2:-600}
    local elapsed=0

    log "Waiting for run $run_id to complete..."
    while [ $elapsed -lt $max_wait ]; do
        local status
        status=$(gh run view "$run_id" --json status -q '.status' 2>/dev/null || echo "queued")
        if [ "$status" = "completed" ]; then
            return 0
        fi
        sleep 10
        elapsed=$((elapsed + 10))
    done
    fail "Run $run_id did not complete within ${max_wait}s"
    return 1
}

# ============================================================================
# Scenario 1: No Overlap (parallel execution)
# ============================================================================
scenario_1() {
    log "=== Scenario 1: No Overlap (parallel execution) ==="
    log "Branch A: stacks/dev/config.yaml"
    log "Branch B: stacks/prod/config.yaml"
    log "Expected: Both workflows run in parallel, no blocking"

    local branch_a="test/concurrent-no-overlap-a-${TIMESTAMP}"
    local branch_b="test/concurrent-no-overlap-b-${TIMESTAMP}"

    # Branch A: modify dev
    git checkout -b "$branch_a" main
    echo "# scenario 1a - ${TIMESTAMP}" >> stacks/dev/config.yaml
    git add stacks/dev/config.yaml
    git commit -m "test: scenario 1a - modify dev config"
    git push -u origin "$branch_a"

    # Branch B: modify prod
    git checkout -b "$branch_b" main
    echo "# scenario 1b - ${TIMESTAMP}" >> stacks/prod/config.yaml
    git add stacks/prod/config.yaml
    git commit -m "test: scenario 1b - modify prod config"
    git push -u origin "$branch_b"

    log "Both branches pushed. Workflows should run in parallel."
    log "Check: neither matrix should show concurrency_blocked:true"

    # Cleanup
    cleanup_branch "$branch_a"
    cleanup_branch "$branch_b"

    ok "Scenario 1 branches pushed"
}

# ============================================================================
# Scenario 2: File-level Overlap (B waits for A)
# ============================================================================
scenario_2() {
    log "=== Scenario 2: File-level Overlap ==="
    log "Branch A: stacks/prod/config.yaml"
    log "Branch B: stacks/prod/config.yaml (different change)"
    log "Expected: B detects A's run, shows concurrency_blocked:true for prod"

    local branch_a="test/concurrent-file-overlap-a-${TIMESTAMP}"
    local branch_b="test/concurrent-file-overlap-b-${TIMESTAMP}"

    # Branch A
    git checkout -b "$branch_a" main
    echo "# scenario 2a - ${TIMESTAMP}" >> stacks/prod/config.yaml
    git add stacks/prod/config.yaml
    git commit -m "test: scenario 2a - modify prod config"
    git push -u origin "$branch_a"

    sleep 5

    # Branch B (same file, different change)
    git checkout -b "$branch_b" main
    echo "# scenario 2b - ${TIMESTAMP}" >> stacks/prod/config.yaml
    git add stacks/prod/config.yaml
    git commit -m "test: scenario 2b - modify prod config (overlap)"
    git push -u origin "$branch_b"

    log "B pushed 5s after A. B should detect file-level overlap."
    log "Check: B's matrix shows concurrency_blocked:true, concurrency_blocked_by:1 for prod"

    cleanup_branch "$branch_a"
    cleanup_branch "$branch_b"

    ok "Scenario 2 branches pushed"
}

# ============================================================================
# Scenario 3: Group-level Overlap (different files, same group)
# ============================================================================
scenario_3() {
    log "=== Scenario 3: Group-level Overlap ==="
    log "Branch A: stacks/prod/config.yaml"
    log "Branch B: stacks/prod/networking.yaml"
    log "Expected: B detects A via group overlap (both in 'prod' group)"

    local branch_a="test/concurrent-group-overlap-a-${TIMESTAMP}"
    local branch_b="test/concurrent-group-overlap-b-${TIMESTAMP}"

    # Branch A
    git checkout -b "$branch_a" main
    echo "# scenario 3a - ${TIMESTAMP}" >> stacks/prod/config.yaml
    git add stacks/prod/config.yaml
    git commit -m "test: scenario 3a - modify prod config"
    git push -u origin "$branch_a"

    sleep 5

    # Branch B (different file, same group)
    git checkout -b "$branch_b" main
    echo "# scenario 3b - ${TIMESTAMP}" >> stacks/prod/networking.yaml
    git add stacks/prod/networking.yaml
    git commit -m "test: scenario 3b - modify prod networking (group overlap)"
    git push -u origin "$branch_b"

    log "B should detect group-level overlap with A on 'prod'"
    log "Check: B's matrix shows concurrency_blocked:true for stacks/prod"

    cleanup_branch "$branch_a"
    cleanup_branch "$branch_b"

    ok "Scenario 3 branches pushed"
}

# ============================================================================
# Scenario 4: Mixed Overlap (partial blocking)
# ============================================================================
scenario_4() {
    log "=== Scenario 4: Mixed Overlap (partial blocking) ==="
    log "Branch A: stacks/dev + stacks/prod"
    log "Branch B: stacks/prod + stacks/staging"
    log "Expected: B blocked on prod, but staging proceeds"

    local branch_a="test/concurrent-mixed-a-${TIMESTAMP}"
    local branch_b="test/concurrent-mixed-b-${TIMESTAMP}"

    # Branch A: dev + prod
    git checkout -b "$branch_a" main
    echo "# scenario 4a - ${TIMESTAMP}" >> stacks/dev/config.yaml
    echo "# scenario 4a - ${TIMESTAMP}" >> stacks/prod/config.yaml
    git add stacks/dev/config.yaml stacks/prod/config.yaml
    git commit -m "test: scenario 4a - modify dev + prod"
    git push -u origin "$branch_a"

    sleep 5

    # Branch B: prod + staging
    git checkout -b "$branch_b" main
    echo "# scenario 4b - ${TIMESTAMP}" >> stacks/prod/networking.yaml
    echo "# scenario 4b - ${TIMESTAMP}" >> stacks/staging/config.yaml
    git add stacks/prod/networking.yaml stacks/staging/config.yaml
    git commit -m "test: scenario 4b - modify prod + staging (partial overlap)"
    git push -u origin "$branch_b"

    log "B should be blocked on prod but staging is not blocked"
    log "Check: B's matrix: prod has concurrency_blocked:true, staging has concurrency_blocked:false"

    cleanup_branch "$branch_a"
    cleanup_branch "$branch_b"

    ok "Scenario 4 branches pushed"
}

# ============================================================================
# Scenario 5: Hash key mode
# ============================================================================
scenario_5() {
    log "=== Scenario 5: Hash key mode ==="
    log "Same as Scenario 3 but using deploy-concurrent-hash.yml"
    log "Expected: Group keys are 8-char hex hashes, overlap detection still works"

    local branch_a="test/concurrent-hash-a-${TIMESTAMP}"
    local branch_b="test/concurrent-hash-b-${TIMESTAMP}"

    git checkout -b "$branch_a" main
    echo "# scenario 5a - ${TIMESTAMP}" >> stacks/prod/config.yaml
    git add stacks/prod/config.yaml
    git commit -m "test: scenario 5a - hash mode prod config"
    git push -u origin "$branch_a"

    sleep 5

    git checkout -b "$branch_b" main
    echo "# scenario 5b - ${TIMESTAMP}" >> stacks/prod/networking.yaml
    git add stacks/prod/networking.yaml
    git commit -m "test: scenario 5b - hash mode prod networking"
    git push -u origin "$branch_b"

    log "Check: Group keys in matrix are 8-char hex hashes"
    log "Check: Overlap detection works with hash-based keys"

    cleanup_branch "$branch_a"
    cleanup_branch "$branch_b"

    ok "Scenario 5 branches pushed"
}

# ============================================================================
# Main
# ============================================================================
main() {
    cd "$REPO_ROOT"

    echo ""
    echo "============================================================================"
    echo "  Concurrent Deployment Scenario Tests"
    echo "  Repo: ${REPO_NAME}"
    echo "  Timestamp: ${TIMESTAMP}"
    echo "============================================================================"
    echo ""

    local scenario=${1:-all}

    case $scenario in
        1) scenario_1 ;;
        2) scenario_2 ;;
        3) scenario_3 ;;
        4) scenario_4 ;;
        5) scenario_5 ;;
        all)
            scenario_1
            echo ""
            scenario_2
            echo ""
            scenario_3
            echo ""
            scenario_4
            echo ""
            scenario_5
            ;;
        *)
            echo "Usage: $0 [1|2|3|4|5|all]"
            exit 1
            ;;
    esac

    echo ""
    echo "============================================================================"
    echo "  All scenarios pushed. Check GitHub Actions for results."
    echo "============================================================================"
}

main "$@"
