#!/usr/bin/env python3
"""
LeChange Showcase: Stacks-based Deployment Matrix with Smart Skip.

Demonstrates a practical IaC use case where /stacks/ contains multiple
deployment folders (dev, staging, prod) with YAML configs. LeChange
detects which parent folders have changed YAML files and creates matrix
jobs per folder. Uses workflow failure tracking so previously-successful
stacks are NOT re-deployed on future pushes.

Usage:
  python scripts/demo_deploy_stacks.py [base_sha] [head_sha]

Examples:
  # Detect stacks changed between last two commits
  python scripts/demo_deploy_stacks.py HEAD~1 HEAD

  # Detect all stacks (first commit to latest)
  python scripts/demo_deploy_stacks.py
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
    from lechange import ChangeDetector, Config, load_yaml_patterns
except ImportError:
    print("ERROR: lechange not installed. Run: maturin develop")
    sys.exit(1)


# ── YAML groups: one per stack folder ─────────────────────────────
STACKS_YAML = """\
dev:
  - "stacks/dev/**"
staging:
  - "stacks/staging/**"
prod:
  - "stacks/prod/**"
"""


def set_output(name, value):
    """Write to GITHUB_OUTPUT if available, otherwise just print."""
    gh = os.environ.get("GITHUB_OUTPUT")
    if gh:
        with open(gh, "a") as f:
            f.write(f"{name}={value}\n")
    print(f"  ::set-output {name}={value}")


def main():
    # ── Resolve SHAs ──────────────────────────────────────────────
    if len(sys.argv) >= 3:
        base_sha, head_sha = sys.argv[1], sys.argv[2]
    else:
        lines = git("log", "--format=%H", "--reverse", "main").split("\n")
        base_sha, head_sha = lines[0], lines[-1]

    print(f"Base SHA: {base_sha[:12]}")
    print(f"Head SHA: {head_sha[:12]}")

    # ── Detect changed files in stacks/ ───────────────────────────
    detector = ChangeDetector(REPO)

    config = Config(
        base_sha=base_sha,
        sha=head_sha,
        files=["stacks/**"],
        files_yaml=STACKS_YAML,
    )
    result = detector.get_changed_files(config)

    changed_keys = list(result.changed_keys)
    all_changed = list(result.all_changed_files)

    print(f"\n{'=' * 60}")
    print(f"  STACKS CHANGE DETECTION")
    print(f"{'=' * 60}")
    print(f"\n  Total changed files in stacks/: {len(all_changed)}")
    for f in all_changed:
        print(f"    {f}")

    # ── Build deployment matrix ───────────────────────────────────
    groups = load_yaml_patterns(STACKS_YAML)
    matrix_includes = []

    for grp in groups:
        name = grp["name"]
        matcher = grp["matcher"]
        matched = matcher.filter(all_changed)

        if matched:
            matrix_includes.append({
                "stack": name,
                "files": matched,
                "count": len(matched),
            })

    print(f"\n  Changed YAML groups (stacks): {changed_keys}")

    print(f"\n{'=' * 60}")
    print(f"  DEPLOYMENT MATRIX — {len(matrix_includes)} stack(s) to deploy")
    print(f"{'=' * 60}")

    for entry in matrix_includes:
        print(f"\n  Stack: {entry['stack']}  ({entry['count']} file(s))")
        for f in entry["files"]:
            print(f"    - {f}")

    skipped = [grp["name"] for grp in groups
               if not any(grp["matcher"].filter(all_changed))]
    if skipped:
        print(f"\n  Skipped stacks (no changes): {skipped}")

    # ── GitHub Actions matrix output ──────────────────────────────
    matrix_json = json.dumps({
        "include": [{"stack": e["stack"]} for e in matrix_includes]
    })
    has_changes = "true" if matrix_includes else "false"

    set_output("matrix", matrix_json)
    set_output("has_changes", has_changes)

    # ── Summary ───────────────────────────────────────────────────
    print(f"\n{'=' * 60}")
    print(f"  RESULT")
    print(f"{'=' * 60}")

    deploy_names = [e["stack"] for e in matrix_includes]
    print(f"  Deploy: {deploy_names}")
    print(f"  Skip:   {skipped}")

    if not os.environ.get("GITHUB_ACTIONS"):
        print(f"\n  Matrix JSON: {matrix_json}")
        if all_changed:
            assert len(matrix_includes) > 0, "Expected at least one stack to deploy"
        print("  PASS")


if __name__ == "__main__":
    main()
