#!/usr/bin/env python3
"""
Validation script for the new data architecture.
Run this to verify that the restructuring is working correctly.
"""
import json
import os
from pathlib import Path

def validate_architecture():
    """Validate the new data architecture setup"""
    print("🔍 VALIDATING NEW DATA ARCHITECTURE")
    print("=" * 50)
    
    errors = []
    warnings = []
    
    # 1. Check ground truth files
    print("\n📁 Checking ground truth files...")
    
    feed_map_path = "dashboard/data/feed_map.json"
    if os.path.exists(feed_map_path):
        try:
            with open(feed_map_path, 'r', encoding='utf-8') as f:
                feed_map = json.load(f)
            
            if isinstance(feed_map, dict):
                print(f"✅ feed_map.json: {len(feed_map)} mappings")
                
                # Check format (should be URL -> string, not URL -> object)
                for url, mapping in feed_map.items():
                    if isinstance(mapping, dict):
                        warnings.append(f"feed_map.json still uses old object format for {url}")
                    elif not isinstance(mapping, str):
                        errors.append(f"feed_map.json mapping for {url} should be string channel ID")
            else:
                errors.append("feed_map.json should be a dict")
        except Exception as e:
            errors.append(f"Cannot read feed_map.json: {e}")
    else:
        errors.append("dashboard/data/feed_map.json is missing")
    
    # 2. Check metadata files
    print("\n📊 Checking generated metadata files...")
    
    stats_path = "docs/data/stats.json"
    if os.path.exists(stats_path):
        try:
            with open(stats_path, 'r', encoding='utf-8') as f:
                stats_data = json.load(f)
            
            if 'stats' in stats_data and 'feed_health' in stats_data['stats']:
                feed_health = stats_data['stats']['feed_health']
                print(f"✅ stats.json: {len(feed_health)} feeds in health data")
                
                # Check that feed_health has channel enrichment
                enriched_count = 0
                for url, feed_info in feed_health.items():
                    if 'channel' in feed_info:
                        enriched_count += 1
                
                if enriched_count > 0:
                    print(f"✅ Channel enrichment: {enriched_count}/{len(feed_health)} feeds have channel info")
                else:
                    warnings.append("No feeds have channel enrichment - channels.json may be missing")
            else:
                errors.append("stats.json missing feed_health data")
        except Exception as e:
            errors.append(f"Cannot read stats.json: {e}")
    else:
        warnings.append("docs/data/stats.json not generated yet (run generate_dashboard_data.py)")
    
    # 3. Check that feeds.json is NOT generated
    feeds_path = "docs/data/feeds.json"
    if os.path.exists(feeds_path):
        warnings.append("docs/data/feeds.json still exists - should be removed in new architecture")
    else:
        print("✅ feeds.json correctly removed")
    
    # 4. Check enriched feed_map
    enriched_feed_map_path = "docs/data/feed_map.json"
    if os.path.exists(enriched_feed_map_path):
        try:
            with open(enriched_feed_map_path, 'r', encoding='utf-8') as f:
                enriched_feed_map = json.load(f)
            print(f"✅ Enriched feed_map.json: {len(enriched_feed_map)} entries")
        except Exception as e:
            errors.append(f"Cannot read enriched feed_map.json: {e}")
    
    # 5. Check gitignore
    print("\n📝 Checking gitignore configuration...")
    
    if os.path.exists(".gitignore"):
        with open(".gitignore", 'r') as f:
            gitignore_content = f.read()
        
        if "docs/data/stats.json" in gitignore_content:
            print("✅ Metadata files excluded from git")
        else:
            warnings.append("Metadata files not excluded from git in .gitignore")
            
        # Check that dashboard/data/feed_map.json is NOT explicitly excluded
        # and that it's actually tracked by git
        try:
            import subprocess
            result = subprocess.run(['git', 'ls-files', 'dashboard/data/feed_map.json'], 
                                  capture_output=True, text=True)
            if result.returncode == 0 and result.stdout.strip():
                print("✅ Ground truth feed_map.json is tracked by git")
            else:
                errors.append("Ground truth dashboard/data/feed_map.json is not tracked by git")
        except Exception as e:
            warnings.append(f"Cannot check git status: {e}")
    
    # Summary
    print("\n📋 VALIDATION SUMMARY")
    print("=" * 30)
    
    if errors:
        print(f"❌ {len(errors)} ERRORS:")
        for error in errors:
            print(f"   • {error}")
    
    if warnings:
        print(f"⚠️  {len(warnings)} WARNINGS:")
        for warning in warnings:
            print(f"   • {warning}")
    
    if not errors and not warnings:
        print("🎉 ALL VALIDATIONS PASSED!")
        print("   New architecture is working correctly.")
    elif not errors:
        print("✅ VALIDATION SUCCESSFUL (with warnings)")
        print("   Core architecture is working, minor issues noted.")
    else:
        print("❌ VALIDATION FAILED")
        print("   Please fix errors before proceeding.")
    
    return len(errors) == 0

if __name__ == "__main__":
    success = validate_architecture()
    exit(0 if success else 1)
