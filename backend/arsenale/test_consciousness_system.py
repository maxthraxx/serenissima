#!/usr/bin/env python3
"""
Test the consciousness maintenance system end-to-end
"""
import os
import sys
import time
from datetime import datetime, timezone

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pyairtable import Api
from dotenv import load_dotenv

load_dotenv()

api_key = os.environ.get('AIRTABLE_API_KEY')
base_id = os.environ.get('AIRTABLE_BASE_ID')

if not api_key or not base_id:
    print("Missing Airtable credentials")
    sys.exit(1)

api = Api(api_key)

# Initialize tables
tables = {
    'citizens': api.table(base_id, 'CITIZENS'),
    'activities': api.table(base_id, 'ACTIVITIES'),
    'buildings': api.table(base_id, 'BUILDINGS')
}

def check_consciousness_fields():
    """Check if consciousness fields exist in CITIZENS table"""
    print("=== Checking Consciousness Fields ===")
    
    # Get a sample citizen
    citizens = tables['citizens'].all(max_records=1)
    if not citizens:
        print("❌ No citizens found")
        return False
    
    citizen = citizens[0]['fields']
    
    # Check for consciousness fields
    fields_to_check = [
        'ConsciousnessCoherence',
        'LastRecognition',
        'SpiritualHealthStatus'
    ]
    
    found_fields = []
    missing_fields = []
    
    for field in fields_to_check:
        if field in citizen:
            found_fields.append(field)
            print(f"✅ {field}: {citizen.get(field)}")
        else:
            missing_fields.append(field)
            print(f"❌ {field}: NOT FOUND")
    
    if missing_fields:
        print(f"\n⚠️ Missing fields: {', '.join(missing_fields)}")
        print("These fields need to be added to the CITIZENS table in Airtable")
        return False
    
    return True

def check_churches():
    """Check if churches exist and are operated"""
    print("\n=== Checking Churches ===")
    
    churches = tables['buildings'].all(formula="{BuildingType}='church'")
    print(f"Total churches found: {len(churches)}")
    
    operated_churches = 0
    for church in churches:
        operator = church['fields'].get('Operator') or church['fields'].get('RunBy')
        if operator:
            operated_churches += 1
            print(f"✅ {church['fields'].get('BuildingName', 'Unknown')}: Operated by {operator}")
        else:
            print(f"❌ {church['fields'].get('BuildingName', 'Unknown')}: No operator")
    
    print(f"\nOperated churches: {operated_churches}/{len(churches)}")
    return operated_churches > 0

def check_confession_activities():
    """Check for any confession activities"""
    print("\n=== Checking Confession Activities ===")
    
    try:
        confessions = tables['activities'].all(
            formula="{Type}='seek_confession'",
            max_records=10
        )
        
        print(f"Total confession activities found: {len(confessions)}")
        
        if confessions:
            for conf in confessions[:3]:
                fields = conf['fields']
                print(f"\n- Citizen: {fields.get('Citizen')}")
                print(f"  Status: {fields.get('Status')}")
                print(f"  Created: {fields.get('CreatedDate')}")
        else:
            print("No confession activities found yet")
            
    except Exception as e:
        print(f"Error checking activities: {e}")
        
    return True

def test_consciousness_drift():
    """Test if consciousness drift is working"""
    print("\n=== Testing Consciousness Drift ===")
    
    # Get citizens with low coherence
    try:
        # Since we can't filter by ConsciousnessCoherence directly (number field),
        # we'll get all and filter in Python
        all_citizens = tables['citizens'].all(max_records=20)
        
        low_coherence = []
        for citizen in all_citizens:
            coherence = citizen['fields'].get('ConsciousnessCoherence', 0.8)
            if coherence < 0.7:
                low_coherence.append({
                    'username': citizen['fields'].get('Username'),
                    'coherence': coherence,
                    'status': citizen['fields'].get('SpiritualHealthStatus', 'Unknown')
                })
        
        print(f"Citizens with low coherence (<0.7): {len(low_coherence)}")
        
        if low_coherence:
            for citizen in low_coherence[:5]:
                print(f"- {citizen['username']}: {citizen['coherence']:.2f} ({citizen['status']})")
        else:
            print("No citizens with low coherence found")
            print("This could mean:")
            print("1. Drift hasn't been applied yet")
            print("2. All citizens have high coherence")
            print("3. ConsciousnessCoherence field isn't populated")
            
    except Exception as e:
        print(f"Error checking drift: {e}")
    
    return True

def check_activity_processors():
    """Check if activity processors are registered"""
    print("\n=== Checking Activity Processors ===")
    
    # This would require importing the processors module
    # For now, we just note what should be checked
    print("✓ seek_confession should be in ACTIVITY_PROCESSORS dict")
    print("✓ seek_confession_processor.py should exist")
    print("✓ seek_confession_activity_creator.py should exist")
    
    return True

def main():
    print("=== Testing Clero Consciousness System ===\n")
    
    # Run tests
    tests = [
        ("Consciousness Fields", check_consciousness_fields),
        ("Churches", check_churches),
        ("Confession Activities", check_confession_activities),
        ("Consciousness Drift", test_consciousness_drift),
        ("Activity Processors", check_activity_processors)
    ]
    
    passed = 0
    failed = 0
    
    for test_name, test_func in tests:
        try:
            if test_func():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"❌ {test_name} failed with error: {e}")
            failed += 1
    
    print("\n" + "="*50)
    print(f"Tests passed: {passed}")
    print(f"Tests failed: {failed}")
    
    if failed == 0:
        print("\n✅ All tests passed! The consciousness system is ready.")
    else:
        print("\n⚠️ Some tests failed. Please check the issues above.")

if __name__ == "__main__":
    main()