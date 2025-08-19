#!/usr/bin/env python3
"""
Test script to create a seen.json file and verify upload logic
"""
import os
import json
import sys
from pathlib import Path

# Add the parent directory to path so we can import bot modules
sys.path.insert(0, str(Path(__file__).parent.parent))

def create_test_seen_json():
    """Create a test seen.json file"""
    test_guids = [
        "test-guid-1",
        "test-guid-2", 
        "test-guid-3"
    ]
    
    with open('seen.json', 'w') as f:
        json.dump(test_guids, f, indent=2)
    
    print(f"✅ Created test seen.json with {len(test_guids)} GUIDs")
    return True

def test_save_seen_guids():
    """Test the save_seen_guids function from bot/main.py"""
    try:
        from bot.main import save_seen_guids
        
        test_guids = {
            "test-guid-1",
            "test-guid-2", 
            "test-guid-3",
            "test-guid-4"
        }
        
        print(f"🧪 Testing save_seen_guids with {len(test_guids)} GUIDs...")
        save_seen_guids(test_guids)
        
        # Check if file was created
        if os.path.exists('seen.json'):
            with open('seen.json', 'r') as f:
                saved_data = json.load(f)
            print(f"✅ save_seen_guids created seen.json with {len(saved_data)} entries")
            print(f"📄 Contents: {saved_data}")
            return True
        else:
            print("❌ seen.json was not created")
            return False
            
    except Exception as e:
        print(f"❌ Error testing save_seen_guids: {e}")
        return False

def check_r2_config():
    """Check if R2 configuration is available"""
    try:
        from bot.config import r2_client, SEEN_R2_BUCKET
        
        print(f"🔧 SEEN_R2_BUCKET: {SEEN_R2_BUCKET}")
        
        client = r2_client()
        if client:
            print("✅ R2 client configured")
            return True
        else:
            print("❌ R2 client not configured")
            return False
            
    except Exception as e:
        print(f"❌ Error checking R2 config: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Testing seen.json creation and upload logic...")
    print()
    
    # Test 1: Check R2 configuration
    print("1️⃣ Checking R2 configuration...")
    r2_ok = check_r2_config()
    print()
    
    # Test 2: Test save_seen_guids function
    print("2️⃣ Testing save_seen_guids function...")
    save_ok = test_save_seen_guids()
    print()
    
    # Test 3: Create manual test file
    print("3️⃣ Creating manual test seen.json...")
    manual_ok = create_test_seen_json()
    print()
    
    print("📊 Summary:")
    print(f"  R2 Config: {'✅' if r2_ok else '❌'}")
    print(f"  save_seen_guids: {'✅' if save_ok else '❌'}")
    print(f"  Manual creation: {'✅' if manual_ok else '❌'}")
    
    if os.path.exists('seen.json'):
        print()
        print("📄 Current seen.json contents:")
        with open('seen.json', 'r') as f:
            print(f.read())
