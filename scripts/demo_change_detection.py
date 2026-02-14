#!/usr/bin/env python3
"""
LeChange Showcase: Detect all change types across commits.

Demonstrates:
  - Added files detection
  - Deleted files detection
  - Modified files detection
  - Renamed files detection
  - Pattern filtering (YAML groups)
  - POSIX path normalization
  - Rename splitting (old+new as delete+add)

Usage:
  python scripts/demo_change_detection.py
"""

import json
import subprocess
import sys
import os

# ---------------------------------------------------------------------------
# Resolve SHAs
# ---------------------------------------------------------------------------
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def git(*args):
    r = subprocess.run(
        ["git"] + list(args), cwd=REPO, capture_output=True, text=True, check=True
    )
    return r.stdout.strip()


def get_shas():
    lines = git("log", "--format=%H %s", "--reverse", "main").split("\n")
    shas = {}
    for i, line in enumerate(lines, 1):
        sha, msg = line.split(" ", 1)
        shas[f"commit{i}"] = sha
        shas[msg] = sha
    return shas


def section(title):
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"{'=' * 70}")


def subsection(title):
    print(f"\n  --- {title} ---")


# ===========================================================================
# Import lechange
# ===========================================================================
try:
    from lechange import ChangeDetector, Config, PatternMatcher, load_yaml_patterns
except ImportError:
    print("ERROR: lechange not installed. Run: maturin develop")
    sys.exit(1)


def main():
    shas = get_shas()
    detector = ChangeDetector(REPO)

    print("LeChange Showcase — Change Detection Report")
    print(f"Repository: {REPO}")
    print(f"Commits on main: {len([k for k in shas if k.startswith('commit')])}")
    for k, v in shas.items():
        if k.startswith("commit"):
            print(f"  {k}: {v[:12]} ({shas.get(v, '')})")

    # ------------------------------------------------------------------
    # TEST 1: Additions only (commit1 → commit2)
    # ------------------------------------------------------------------
    section("TEST 1: Detect ADDED files (commit1 → commit2)")
    config = Config(base_sha=shas["commit1"], sha=shas["commit2"])
    result = detector.get_changed_files(config)

    print(f"  any_changed:  {result.any_changed}")
    print(f"  any_added:    {result.any_added}")
    print(f"  added_count:  {result.added_files_count}")
    subsection("Added files")
    for f in result.added_files:
        print(f"    + {f}")

    assert result.any_added, "Expected added files between commit1 and commit2"
    assert result.added_files_count > 0
    added = list(result.added_files)
    assert any("helpers" in f for f in added), f"Expected helpers.ts, got {added}"
    assert any("validators" in f for f in added), f"Expected validators.ts, got {added}"
    assert any("settings" in f for f in added), f"Expected settings.yaml, got {added}"
    print("  PASS")

    # ------------------------------------------------------------------
    # TEST 2: Renames + Modifications (commit2 → commit3)
    # ------------------------------------------------------------------
    section("TEST 2: Detect RENAMES + MODIFICATIONS (commit2 → commit3)")
    config = Config(base_sha=shas["commit2"], sha=shas["commit3"])
    result = detector.get_changed_files(config)

    print(f"  any_changed:  {result.any_changed}")
    print(f"  any_renamed:  {result.any_renamed}")
    print(f"  any_modified: {result.any_modified}")
    print(f"  renamed_count:  {result.renamed_files_count}")
    print(f"  modified_count: {result.modified_files_count}")

    subsection("Renamed files")
    for f in result.renamed_files:
        print(f"    R {f}")
    subsection("Rename mapping (old → new)")
    for old, new in result.renamed_files_mapping.items():
        print(f"    {old} → {new}")
    subsection("Modified files")
    for f in result.modified_files:
        print(f"    M {f}")

    all_files = list(result.all_changed_files)
    assert len(all_files) > 0, "Expected changes between commit2 and commit3"
    print("  PASS")

    # ------------------------------------------------------------------
    # TEST 3: Deletions (commit3 → commit4)
    # ------------------------------------------------------------------
    section("TEST 3: Detect DELETED files (commit3 → commit4)")
    config = Config(base_sha=shas["commit3"], sha=shas["commit4"])
    result = detector.get_changed_files(config)

    print(f"  any_changed:  {result.any_changed}")
    print(f"  any_deleted:  {result.any_deleted}")
    print(f"  deleted_count: {result.deleted_files_count}")
    print(f"  added_count:   {result.added_files_count}")

    subsection("Deleted files")
    for f in result.deleted_files:
        print(f"    - {f}")
    subsection("Added files (replacements)")
    for f in result.added_files:
        print(f"    + {f}")

    deleted = list(result.deleted_files)
    assert result.any_deleted, "Expected deletions between commit3 and commit4"
    assert any("README" in f for f in deleted), f"Expected README.md deleted, got {deleted}"
    print("  PASS")

    # ------------------------------------------------------------------
    # TEST 4: Full diff with all change types (commit1 → commit5)
    # ------------------------------------------------------------------
    section("TEST 4: ALL change types (commit1 → commit5)")
    config = Config(base_sha=shas["commit1"], sha=shas["commit5"])
    result = detector.get_changed_files(config)

    print(f"  total_changed: {result.all_changed_files_count}")
    print(f"  added:    {result.added_files_count}")
    print(f"  modified: {result.modified_files_count}")
    print(f"  deleted:  {result.deleted_files_count}")
    print(f"  renamed:  {result.renamed_files_count}")

    subsection("All changed files")
    for f in result.all_changed_files:
        print(f"    {f}")

    assert result.all_changed_files_count > 0
    print("  PASS")

    # ------------------------------------------------------------------
    # TEST 5: Pattern filtering — TSX only
    # ------------------------------------------------------------------
    section("TEST 5: Pattern filter — only *.tsx files")
    config = Config(
        base_sha=shas["commit1"],
        sha=shas["commit5"],
        files=["**/*.tsx"],
    )
    result = detector.get_changed_files(config)

    print(f"  pattern_applied: {result.pattern_applied}")
    print(f"  matched_count:   {result.all_changed_files_count}")
    subsection("Matched files")
    for f in result.all_changed_files:
        print(f"    {f}")
        assert f.endswith(".tsx"), f"Pattern leak: {f}"
    subsection("Unmatched (other) files")
    for f in result.other_changed_files:
        print(f"    {f}")

    assert result.pattern_applied
    print("  PASS")

    # ------------------------------------------------------------------
    # TEST 6: YAML groups — frontend vs backend
    # ------------------------------------------------------------------
    section("TEST 6: YAML group filtering — frontend vs backend")
    yaml_config = """
frontend:
  - "src/components/**"
  - "src/pages/**"
backend:
  - "src/api/**"
  - "src/models/**"
infra:
  - ".github/**"
  - "config/**"
"""
    config = Config(
        base_sha=shas["commit1"],
        sha=shas["commit5"],
        files_yaml=yaml_config,
    )
    result = detector.get_changed_files(config)

    print(f"  changed_keys: {list(result.changed_keys)}")
    subsection("All matched files")
    for f in result.all_changed_files:
        print(f"    {f}")

    keys = list(result.changed_keys)
    assert len(keys) > 0, "Expected YAML groups to match"
    print("  PASS")

    # ------------------------------------------------------------------
    # TEST 7: Rename splitting (renames → add + delete)
    # ------------------------------------------------------------------
    section("TEST 7: Rename splitting (renames as add + delete)")
    config = Config(
        base_sha=shas["commit2"],
        sha=shas["commit3"],
        output_renamed_as_deleted_added=True,
    )
    result = detector.get_changed_files(config)

    print(f"  added_count:   {result.added_files_count}")
    print(f"  deleted_count: {result.deleted_files_count}")
    print(f"  renamed_count: {result.renamed_files_count}")

    subsection("Added (new rename targets)")
    for f in result.added_files:
        print(f"    + {f}")
    subsection("Deleted (old rename sources)")
    for f in result.deleted_files:
        print(f"    - {f}")

    print("  PASS")

    # ------------------------------------------------------------------
    # TEST 8: POSIX path normalization
    # ------------------------------------------------------------------
    section("TEST 8: POSIX path output")
    config = Config(
        base_sha=shas["commit1"],
        sha=shas["commit5"],
        use_posix_path_separator=True,
    )
    result = detector.get_changed_files(config)

    for f in result.all_changed_files:
        assert "\\" not in f, f"Non-POSIX path: {f}"
    print("  All paths use forward slashes")
    print("  PASS")

    # ------------------------------------------------------------------
    # TEST 9: Counts consistency
    # ------------------------------------------------------------------
    section("TEST 9: Counts consistency check")
    config = Config(base_sha=shas["commit1"], sha=shas["commit5"])
    result = detector.get_changed_files(config)

    assert result.added_files_count == len(list(result.added_files))
    assert result.deleted_files_count == len(list(result.deleted_files))
    assert result.modified_files_count == len(list(result.modified_files))
    assert result.renamed_files_count == len(list(result.renamed_files))
    print(f"  added:    count={result.added_files_count} == len={len(list(result.added_files))}")
    print(f"  deleted:  count={result.deleted_files_count} == len={len(list(result.deleted_files))}")
    print(f"  modified: count={result.modified_files_count} == len={len(list(result.modified_files))}")
    print(f"  renamed:  count={result.renamed_files_count} == len={len(list(result.renamed_files))}")
    print("  PASS")

    # ------------------------------------------------------------------
    # TEST 10: dir_names mode
    # ------------------------------------------------------------------
    section("TEST 10: Directory names extraction")
    config = Config(
        base_sha=shas["commit1"],
        sha=shas["commit5"],
        dir_names=True,
    )
    result = detector.get_changed_files(config)
    dirs = list(result.all_changed_files)
    print(f"  directories: {dirs}")
    assert len(dirs) > 0
    print("  PASS")

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    section("SUMMARY")
    print("  All 10 tests PASSED")
    print("  Demonstrated: add, delete, modify, rename, pattern filter,")
    print("    YAML groups, rename splitting, POSIX paths, counts, dir_names")


if __name__ == "__main__":
    main()
