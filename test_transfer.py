#!/usr/bin/env python3
"""Test script to compare direct 1 train vs transfer to 2/3 at Chambers."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from subway_agent.mta_feed import get_arrivals
from subway_agent.stations import find_station
from subway_agent.tools import plan_trip_with_transfers

def compare_routes():
    """Compare direct 1 train vs transfer to 2/3 at Chambers."""
    
    # Constants
    SOUTH_FERRY_TO_CHAMBERS = 8  # minutes
    CHAMBERS_TO_PENN_ON_1 = 6    # minutes local
    CHAMBERS_TO_PENN_ON_EXPRESS = 4  # minutes express (2/3)
    TRANSFER_BUFFER = 2  # minutes to make connection
    
    print("=" * 60)
    print("Comparing: Direct 1 train vs Transfer to 2/3 at Chambers")
    print("Route: South Ferry → Penn Station")
    print("=" * 60)
    print()
    
    # Step 1: Get next 1 train departure from South Ferry
    print("Step 1: Checking 1 train arrivals at South Ferry...")
    south_ferry_arrivals = get_arrivals("south_ferry", ["1"])
    northbound_1 = [a for a in south_ferry_arrivals if a.direction == "N"]
    
    if not northbound_1:
        print("❌ No upcoming northbound 1 trains at South Ferry.")
        print("   MTA feed may be unavailable or no trains scheduled.")
        return
    
    next_1_train = northbound_1[0]
    depart_time = next_1_train.minutes_until
    print(f"   ✓ Next 1 train departs in {depart_time} minutes")
    print()
    
    # Step 2: Calculate arrival at Chambers
    arrive_at_chambers = depart_time + SOUTH_FERRY_TO_CHAMBERS
    print(f"Step 2: Will arrive at Chambers St in {arrive_at_chambers} minutes")
    print()
    
    # Step 3: Get 2/3 arrivals at Chambers
    print("Step 3: Checking 2/3 train arrivals at Chambers St...")
    chambers_arrivals = get_arrivals("chambers_123", ["2", "3"])
    northbound_express = [a for a in chambers_arrivals if a.direction == "N"]
    
    if not northbound_express:
        print("   ⚠️  No upcoming northbound 2/3 trains at Chambers St")
        print()
        print("=" * 60)
        print("RESULT: Direct 1 train is the only option")
        direct_total = depart_time + SOUTH_FERRY_TO_CHAMBERS + CHAMBERS_TO_PENN_ON_1
        print(f"Total time: {direct_total} minutes")
        print("=" * 60)
        return
    
    print(f"   ✓ Found {len(northbound_express)} upcoming 2/3 trains")
    for i, arr in enumerate(northbound_express[:5], 1):
        print(f"      {i}. {arr.line} train in {arr.minutes_until} min")
    print()
    
    # Step 4: Filter to trains arriving AFTER user reaches Chambers + buffer
    min_connection_time = arrive_at_chambers + TRANSFER_BUFFER
    valid_express = [a for a in northbound_express if a.minutes_until >= min_connection_time]
    
    print(f"Step 4: Need to catch train after {min_connection_time} minutes (arrival + {TRANSFER_BUFFER} min buffer)")
    if valid_express:
        print(f"   ✓ {len(valid_express)} valid connection(s) available")
    else:
        print("   ⚠️  No valid connections - would need to wait for later train")
    print()
    
    # Step 5: Calculate total time for direct option (stay on 1)
    direct_total = depart_time + SOUTH_FERRY_TO_CHAMBERS + CHAMBERS_TO_PENN_ON_1
    
    # Step 6: Calculate total time for transfer option
    if valid_express:
        next_express = valid_express[0]
        express_depart = next_express.minutes_until
        transfer_total = express_depart + CHAMBERS_TO_PENN_ON_EXPRESS
        transfer_line = next_express.line
        transfer_available = True
    else:
        # Use the next available express even if we have to wait
        if northbound_express:
            next_express = northbound_express[0]
            express_depart = next_express.minutes_until
            # Add wait time if we arrive before the train
            wait_time = max(0, express_depart - arrive_at_chambers - TRANSFER_BUFFER)
            transfer_total = express_depart + wait_time + CHAMBERS_TO_PENN_ON_EXPRESS
            transfer_line = next_express.line
            transfer_available = True
        else:
            transfer_total = None
            transfer_line = "2/3"
            transfer_available = False
    
    # Step 7: Display results
    print("=" * 60)
    print("COMPARISON RESULTS")
    print("=" * 60)
    print()
    print(f"Option 1 (Direct):")
    print(f"  • Take 1 train from South Ferry")
    print(f"  • Stay on 1 train to Penn Station")
    print(f"  • Total time: {direct_total} minutes")
    print(f"    - Wait for 1 train: {depart_time} min")
    print(f"    - South Ferry → Chambers: {SOUTH_FERRY_TO_CHAMBERS} min")
    print(f"    - Chambers → Penn (local): {CHAMBERS_TO_PENN_ON_1} min")
    print()
    
    if transfer_available:
        wait_time = max(0, express_depart - arrive_at_chambers - TRANSFER_BUFFER)
        print(f"Option 2 (Transfer):")
        print(f"  • Take 1 train from South Ferry to Chambers")
        print(f"  • Transfer to {transfer_line} express at Chambers")
        print(f"  • Total time: {transfer_total} minutes")
        print(f"    - Wait for 1 train: {depart_time} min")
        print(f"    - South Ferry → Chambers: {SOUTH_FERRY_TO_CHAMBERS} min")
        if wait_time > 0:
            print(f"    - Wait for {transfer_line} train: {wait_time} min")
        print(f"    - Chambers → Penn (express): {CHAMBERS_TO_PENN_ON_EXPRESS} min")
        print()
        
        print("=" * 60)
        if direct_total <= transfer_total:
            saved = transfer_total - direct_total
            print(f"🏆 RECOMMENDATION: Option 1 (Direct) - saves {saved} minutes")
        else:
            saved = direct_total - transfer_total
            print(f"🏆 RECOMMENDATION: Option 2 (Transfer) - saves {saved} minutes")
        print("=" * 60)
    else:
        print("Option 2 (Transfer): Not available")
        print()
        print("=" * 60)
        print("🏆 RECOMMENDATION: Option 1 (Direct) - only option available")
        print("=" * 60)

if __name__ == "__main__":
    print("Attempting to use agent's built-in comparison tool...")
    print("=" * 60)
    try:
        result = plan_trip_with_transfers.invoke({})
        print(result)
    except Exception as e:
        print(f"Error using tool: {e}")
        print("\nFalling back to manual calculation...")
        print()
        try:
            compare_routes()
        except Exception as e2:
            print(f"Error: {e2}")
            import traceback
            traceback.print_exc()
