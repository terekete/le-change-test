#!/usr/bin/env python3
"""
LeChange Showcase: Generate matrix strategy from changed file groups.

Demonstrates how YAML pattern groups produce a dynamic job matrix
so each group (frontend, backend, infra, tests) runs as a separate
parallel job — and only the groups that actually changed are included.

Usage:
  python scripts/demo_matrix_jobs.py [base_sha] [head_sha]

When run inside GitHub Actions the script writes GITHUB_OUTPUT variables:
  matrix       — JSON matrix for `jobs.<id>.strategy.matrix`
  has_changes  — "true" / "false"
"""

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
    from lechange import ChangeDetector, Config, load_yaml_patterns, format_matrix
except ImportError:
    print("ERROR: lechange not installed. Run: maturin develop")
    sys.exit(1)


# ---------------------------------------------------------------------------
# YAML groups — each group becomes one matrix entry
# ---------------------------------------------------------------------------
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
  - "package.json"
  - ".gitignore"
tests:
  - "tests/**"
"""


def set_output(name, value):
    """Write to GITHUB_OUTPUT if available, otherwise just print."""
    gh = os.environ.get("GITHUB_OUTPUT")
    if gh:
        with open(gh, "a") as f:
            f.write(f"{name}={value}\n")
    print(f"  ::set-output {name}={value}")


def main():
    # Resolve SHAs -----------------------------------------------------------
    if len(sys.argv) >= 3:
        base_sha, head_sha = sys.argv[1], sys.argv[2]
    else:
        # Default: first commit vs last commit on main
        lines = git("log", "--format=%H", "--reverse", "main").split("\n")
        base_sha, head_sha = lines[0], lines[-1]

    print(f"Base SHA: {base_sha[:12]}")
    print(f"Head SHA: {head_sha[:12]}")

    # Detect changes ----------------------------------------------------------
    detector = ChangeDetector(REPO)
    config = Config(
        base_sha=base_sha,
        sha=head_sha,
        files_yaml=YAML_GROUPS,
    )
    result = detector.get_changed_files(config)

    # Build matrix from changed groups ----------------------------------------
    changed_keys = list(result.changed_keys)
    print(f"\nChanged groups: {changed_keys}")

    # Build per-group detail
    groups = load_yaml_patterns(YAML_GROUPS)
    all_changed = set(result.all_changed_files)

    matrix_includes = []
    for grp in groups:
        name = grp["name"]
        matcher = grp["matcher"]
        matched = matcher.filter(list(all_changed))
        if matched:
            matrix_includes.append({
                "group": name,
                "files": matched,
                "count": len(matched),
            })

    # Report ------------------------------------------------------------------
    print(f"\n{'=' * 60}")
    print(f"  MATRIX STRATEGY — {len(matrix_includes)} parallel jobs")
    print(f"{'=' * 60}")

    for entry in matrix_includes:
        print(f"\n  Job: {entry['group']}  ({entry['count']} file(s))")
        for f in entry["files"]:
            print(f"    - {f}")

    # GitHub Actions matrix output
    matrix_json = json.dumps({"include": [{"group": e["group"]} for e in matrix_includes]})
    has_changes = "true" if matrix_includes else "false"

    set_output("matrix", matrix_json)
    set_output("has_changes", has_changes)

    # Also output the full details as a JSON artifact
    details = {
        "base_sha": base_sha[:12],
        "head_sha": head_sha[:12],
        "total_changed": result.all_changed_files_count,
        "groups": [
            {"name": e["group"], "files": e["files"], "count": e["count"]}
            for e in matrix_includes
        ],
    }
    print(f"\n  Full details JSON:")
    print(f"  {json.dumps(details, indent=2)}")

    # Assertions for local testing
    if not os.environ.get("GITHUB_ACTIONS"):
        assert len(matrix_includes) > 0, "Expected at least one group to match"
        group_names = {e["group"] for e in matrix_includes}
        print(f"\n  Groups that would run: {group_names}")
        print("  PASS")


if __name__ == "__main__":
    main()
