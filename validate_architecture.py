#!/usr/bin/env python3
"""
Validation script for the new data architecture.
Ensures configs are not tracked in git and are sourced from R2 under dashboard/data/source.
"""
import json
import os

def validate_architecture():
    print("VALIDATING NEW DATA ARCHITECTURE")
    print("=" * 50)

    errors = []
    warnings = []

    # 1) Authoritative configs presence (as fetched by CI)
    print("\nChecking authoritative source configs...")
    feed_map_path = "dashboard/data/source/feed_map.json"
    channels_path = "dashboard/data/source/channels.json"
    groups_path = "dashboard/data/source/groups.json"
    for p in [feed_map_path, channels_path, groups_path]:
        if not os.path.exists(p):
            warnings.append(f"Missing {p} (CI should fetch from R2 before validation)")

    if os.path.exists(feed_map_path):
        try:
            with open(feed_map_path, 'r', encoding='utf-8') as f:
                fm = json.load(f)
            if not isinstance(fm, dict):
                errors.append("feed_map.json should be a JSON object of feed->channel_id")
        except Exception as e:
            errors.append(f"Cannot read feed_map.json: {e}")

    # 2) Generated dashboard data
    print("\nChecking generated dashboard data...")
    stats_path = "docs/data/stats.json"
    if os.path.exists(stats_path):
        try:
            with open(stats_path, 'r', encoding='utf-8') as f:
                stats_data = json.load(f)
            if 'stats' not in stats_data:
                errors.append("stats.json missing 'stats' root key")
        except Exception as e:
            errors.append(f"Cannot read stats.json: {e}")
    else:
        warnings.append("docs/data/stats.json not generated (run generator)")

    if os.path.exists("docs/data/feeds.json"):
        warnings.append("docs/data/feeds.json should not be generated anymore")
    else:
        print("feeds.json correctly absent")

    # 3) Git ignores
    print("\nChecking .gitignore coverage...")
    if os.path.exists(".gitignore"):
        gi = open(".gitignore", 'r', encoding='utf-8').read()
        if "dashboard/data" in gi and "docs/data" in gi:
            print("Metadata folders excluded from git")
        else:
            warnings.append(".gitignore should exclude dashboard/data and docs/data")

    # Summary
    print("\nVALIDATION SUMMARY")
    print("=" * 30)
    if errors:
        print(f"ERRORS: {len(errors)}")
        for e in errors:
            print(" -", e)
    if warnings:
        print(f"WARNINGS: {len(warnings)}")
        for w in warnings:
            print(" -", w)
    if not errors and not warnings:
        print("ALL VALIDATIONS PASSED")
        return True
    return not errors

if __name__ == "__main__":
    import sys
    sys.exit(0 if validate_architecture() else 1)

