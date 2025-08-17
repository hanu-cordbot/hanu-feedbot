#!/usr/bin/env python3
"""
Quick setup script to handle repository rules and prepare for GitHub Actions testing
"""

import subprocess
import sys
import os
from pathlib import Path

def run_command(cmd, check=True):
    """Run a command and return the result"""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, check=check)
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.CalledProcessError as e:
        return False, e.stdout, e.stderr

def check_git_status():
    """Check current git status"""
    print("🔍 Checking git status...")
    success, stdout, stderr = run_command("git status --porcelain")
    
    if stdout.strip():
        print("⚠️ You have uncommitted changes:")
        print(stdout)
        return False
    
    success, stdout, stderr = run_command("git status")
    print(stdout)
    return True

def create_feature_branch():
    """Create a feature branch for the migration"""
    branch_name = "phase1-migration-setup"
    
    print(f"🌿 Creating feature branch: {branch_name}")
    
    # Check if branch already exists
    success, stdout, stderr = run_command(f"git rev-parse --verify {branch_name}", check=False)
    
    if success:
        print(f"⚠️ Branch {branch_name} already exists. Switching to it...")
        success, stdout, stderr = run_command(f"git checkout {branch_name}")
    else:
        print(f"✅ Creating new branch: {branch_name}")
        success, stdout, stderr = run_command(f"git checkout -b {branch_name}")
    
    if success:
        print(f"✅ Successfully switched to branch: {branch_name}")
        
        # Push the branch to origin
        success, stdout, stderr = run_command(f"git push -u origin {branch_name}", check=False)
        if success:
            print("✅ Feature branch pushed to origin")
        else:
            print("⚠️ Failed to push branch (this is normal if it already exists)")
            print(stderr)
        
        return True
    else:
        print(f"❌ Failed to create/switch to branch: {stderr}")
        return False

def show_next_steps():
    """Show what the user needs to do next"""
    print("\n🎯 NEXT STEPS:")
    print("1. Go to: https://github.com/hanu-cordbot/hanu-feedbot/pulls")
    print("2. Click 'New pull request'")
    print("3. Base: main ← Compare: phase1-migration-setup")
    print("4. Title: 'Phase 1: Complete standalone worker migration'")
    print("5. Create and merge the pull request")
    print("\nOR")
    print("6. Temporarily disable branch protection rules at:")
    print("   https://github.com/hanu-cordbot/hanu-feedbot/settings/branches")
    print("7. Then run: git push origin main")

def main():
    """Main setup function"""
    print("🚀 REPOSITORY SETUP FOR GITHUB ACTIONS TESTING")
    print("=" * 60)
    
    # Check if we're in a git repository
    if not Path(".git").exists():
        print("❌ This doesn't appear to be a git repository")
        print("Please run this script from the project root directory")
        return 1
    
    # Check git status
    if not check_git_status():
        print("❌ Please commit or stash your changes first")
        return 1
    
    # Ask user what they want to do
    print("\n🔧 How would you like to handle the repository rules issue?")
    print("1. Create feature branch and pull request (Recommended)")
    print("2. Show instructions for disabling branch protection")
    print("3. Exit")
    
    choice = input("\nEnter your choice (1-3): ").strip()
    
    if choice == "1":
        if create_feature_branch():
            show_next_steps()
            return 0
        else:
            return 1
    elif choice == "2":
        show_next_steps()
        return 0
    elif choice == "3":
        print("👋 Exiting without changes")
        return 0
    else:
        print("❌ Invalid choice")
        return 1

if __name__ == "__main__":
    sys.exit(main())
