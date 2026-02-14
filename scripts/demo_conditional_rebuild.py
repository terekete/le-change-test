#!/usr/bin/env python3
"""
LeChange Showcase: Branch-based conditional jobs with failure tracking.

Demonstrates:
  1. Detecting which files changed on a feature branch vs main
  2. Using workflow failure tracking to find files that failed in previous CI runs
  3. Building a "rebuild" set = new changes + previously-failed files
  4. Building a "skip" set = files whose tests passed recently (no need to rerun)
  5. Showing the disjoint invariant: rebuild ∩ skip = ∅

This script works in two modes:
  - LOCAL: Simulates workflow tracking by comparing branches
  - CI:    Uses GITHUB_TOKEN for real workflow failure tracking

Usage:
  python scripts/demo_conditional_rebuild.py [--branch feature/add-auth]
"""

import argparse
import json
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def git(*args):
    r = subprocess.run(
        ["git"] + list(args), cwd=REPO, capture_output=True, text=True, check=True
    )
    return r.stdout.strip()


try:
    from lechange import ChangeDetector, Config, load_yaml_patterns
except ImportError:
    print("ERROR: lechange not installed. Run: maturin develop")
    sys.exit(1)

YAML_GROUPS = """
frontend:
  - "src/components/**"
  - "src/pages/**"
  - "**/*.tsx"
backend:
  - "src/api/**"
  - "src/models/**"
  - "src/lib/**"
  - "src/auth/**"
infra:
  - ".github/**"
  - "config/**"
tests:
  - "tests/**"
"""


def section(title):
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"{'=' * 70}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--branch", default="feature/add-auth")
    args = parser.parse_args()

    branch = args.branch
    token = os.environ.get("GITHUB_TOKEN")

    # Find merge base between branch and main
    merge_base = git("merge-base", "main", branch)
    branch_head = git("rev-parse", branch)

    print(f"Branch:     {branch}")
    print(f"Merge base: {merge_base[:12]}")
    print(f"Branch HEAD: {branch_head[:12]}")

    detector = ChangeDetector(REPO)

    # ==================================================================
    # PART 1: What changed on this branch?
    # ==================================================================
    section("PART 1: Files changed on branch vs main")
    config = Config(
        base_sha=merge_base,
        sha=branch_head,
        files_yaml=YAML_GROUPS,
    )
    result = detector.get_changed_files(config)

    print(f"  Total changed: {result.all_changed_files_count}")
    print(f"  Added:   {result.added_files_count}")
    print(f"  Modified: {result.modified_files_count}")
    print(f"  Deleted:  {result.deleted_files_count}")
    print(f"  Renamed:  {result.renamed_files_count}")

    print(f"\n  Changed files:")
    for f in result.all_changed_files:
        print(f"    {f}")

    print(f"\n  Affected groups: {list(result.changed_keys)}")

    # Determine which groups need testing
    groups = load_yaml_patterns(YAML_GROUPS)
    all_changed = set(result.all_changed_files)

    affected = []
    unaffected = []
    for grp in groups:
        matched = grp["matcher"].filter(list(all_changed))
        if matched:
            affected.append({"name": grp["name"], "files": matched})
        else:
            unaffected.append(grp["name"])

    print(f"\n  Groups that NEED testing:")
    for g in affected:
        print(f"    [{g['name']}] {len(g['files'])} file(s): {g['files']}")
    print(f"\n  Groups that can SKIP testing:")
    for name in unaffected:
        print(f"    [{name}] — no changes")

    # ==================================================================
    # PART 2: Workflow failure tracking (CI mode)
    # ==================================================================
    section("PART 2: Workflow failure tracking")

    if token:
        print("  GITHUB_TOKEN found — querying real workflow history")
        os.environ.setdefault("GITHUB_REPOSITORY", "terekete/le-change-test")

        config_wf = Config(
            base_sha=merge_base,
            sha=branch_head,
            token=token,
            track_workflow_failures=True,
            track_job_level=True,
            wait_for_active_workflows=False,
            workflow_max_wait_seconds=15,
            skip_successful_files=True,
        )
        wf_result = detector.get_changed_files(config_wf)

        rebuild = list(wf_result.files_to_rebuild)
        skip = list(wf_result.files_to_skip)
        failed_jobs = list(wf_result.failed_jobs)
        successful_jobs = list(wf_result.successful_jobs)
        reasons = list(wf_result.rebuild_reasons)

        print(f"\n  Files to REBUILD: {len(rebuild)}")
        for f in rebuild:
            print(f"    ! {f}")

        print(f"\n  Files to SKIP (passed recently): {len(skip)}")
        for f in skip:
            print(f"    ~ {f}")

        print(f"\n  Failed jobs: {failed_jobs}")
        print(f"  Successful jobs: {successful_jobs}")

        print(f"\n  Rebuild reasons:")
        for r in reasons:
            print(f"    {r['file']}: {r['kind']} (run_id={r.get('failed_run_id')})")

        # Disjoint invariant
        rebuild_set = set(rebuild)
        skip_set = set(skip)
        overlap = rebuild_set & skip_set
        print(f"\n  Disjoint check: rebuild ∩ skip = {overlap if overlap else '∅'}")
        assert not overlap, f"INVARIANT VIOLATED: {overlap}"

        print(f"\n  Diagnostics:")
        for d in wf_result.diagnostics:
            print(f"    [{d['severity']}] {d['category']}: {d['message']}")
    else:
        print("  No GITHUB_TOKEN — simulating workflow tracking locally")
        print("  (Set GITHUB_TOKEN to enable real workflow API queries)")
        print()
        print("  Simulated scenario:")
        print("    - Pretend 'src/api/router.ts' failed in a previous CI run")
        print("    - New changes on this branch: src/auth/login.ts, src/auth/session.ts")
        print("    - Result: rebuild both auth files (new) + router.ts (prev failure)")
        print()

        simulated_rebuild = list(all_changed) + ["src/api/router.ts"]
        simulated_skip = []

        print(f"  Files to REBUILD: {len(simulated_rebuild)}")
        for f in simulated_rebuild:
            if f in all_changed:
                print(f"    ! {f}  (new change)")
            else:
                print(f"    ! {f}  (previous failure)")

    # ==================================================================
    # PART 3: Final CI decision matrix
    # ==================================================================
    section("PART 3: Final CI Decision")

    # Determine what jobs to run
    jobs_to_run = []
    jobs_to_skip = []

    for grp in groups:
        matched = grp["matcher"].filter(list(all_changed))
        if matched:
            jobs_to_run.append({
                "name": grp["name"],
                "reason": "has_changes",
                "files": matched,
            })
        else:
            jobs_to_skip.append(grp["name"])

    # If workflow tracking found failed files in other groups, add them
    if token:
        rebuild_set = set(wf_result.files_to_rebuild)
        new_change_set = set(result.all_changed_files)
        extra_rebuild = rebuild_set - new_change_set
        if extra_rebuild:
            for grp in groups:
                matched_extra = grp["matcher"].filter(list(extra_rebuild))
                if matched_extra:
                    # Check if group already in jobs_to_run
                    existing = [j for j in jobs_to_run if j["name"] == grp["name"]]
                    if existing:
                        existing[0]["files"].extend(matched_extra)
                        existing[0]["reason"] = "has_changes+prev_failure"
                    else:
                        jobs_to_run.append({
                            "name": grp["name"],
                            "reason": "prev_failure_only",
                            "files": matched_extra,
                        })
                        # Remove from skip list
                        if grp["name"] in jobs_to_skip:
                            jobs_to_skip.remove(grp["name"])

    print(f"\n  Jobs to RUN ({len(jobs_to_run)}):")
    for job in jobs_to_run:
        print(f"    [{job['name']}] reason={job['reason']}, files={len(job['files'])}")
        for f in job["files"]:
            print(f"      - {f}")

    print(f"\n  Jobs to SKIP ({len(jobs_to_skip)}):")
    for name in jobs_to_skip:
        print(f"    [{name}] — no changes, no failures")

    # Output as GitHub Actions matrix
    matrix = {
        "include": [
            {"group": j["name"], "reason": j["reason"]}
            for j in jobs_to_run
        ]
    }
    print(f"\n  GitHub Actions matrix JSON:")
    print(f"  {json.dumps(matrix, indent=2)}")

    section("SUMMARY")
    print(f"  Branch '{branch}' analysis complete:")
    print(f"    - {result.all_changed_files_count} files changed")
    print(f"    - {len(jobs_to_run)} job groups to run")
    print(f"    - {len(jobs_to_skip)} job groups skipped")
    if token:
        print(f"    - Workflow tracking: {len(rebuild)} rebuild, {len(skip)} skip")
    print("  PASS")


if __name__ == "__main__":
    main()
