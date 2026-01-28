#!/usr/bin/env python3
"""Demo script showing the comparison logic with sample data."""

def compare_routes_demo(sample_1_train_minutes=3, sample_express_minutes=[5, 12, 18]):
    """Compare direct 1 train vs transfer to 2/3 at Chambers with sample data."""
    
    # Constants (same as in the actual tool)
    SOUTH_FERRY_TO_CHAMBERS = 8  # minutes
    CHAMBERS_TO_PENN_ON_1 = 6    # minutes local
    CHAMBERS_TO_PENN_ON_EXPRESS = 4  # minutes express (2/3)
    TRANSFER_BUFFER = 2  # minutes to make connection
    
    print("=" * 70)
    print("COMPARISON: Direct 1 train vs Transfer to 2/3 at Chambers")
    print("Route: South Ferry → Penn Station (34th St)")
    print("=" * 70)
    print()
    
    # Step 1: Next 1 train departure
    depart_time = sample_1_train_minutes
    print(f"📊 Scenario: Next 1 train arrives at South Ferry in {depart_time} minutes")
    print()
    
    # Step 2: Calculate arrival at Chambers
    arrive_at_chambers = depart_time + SOUTH_FERRY_TO_CHAMBERS
    print(f"Step 1: Take 1 train from South Ferry")
    print(f"        → Arrive at Chambers St in {arrive_at_chambers} minutes")
    print()
    
    # Step 3: Available express trains
    print(f"Step 2: At Chambers St, check for 2/3 express trains")
    print(f"        Available 2/3 trains arriving in: {sample_express_minutes} minutes")
    print()
    
    # Step 4: Find valid connection
    min_connection_time = arrive_at_chambers + TRANSFER_BUFFER
    print(f"        Need train after {min_connection_time} minutes (arrival + {TRANSFER_BUFFER} min transfer buffer)")
    
    valid_express = [t for t in sample_express_minutes if t >= min_connection_time]
    
    if valid_express:
        next_express = valid_express[0]
        # express_depart is minutes from NOW (when we start), not from when we arrive at Chambers
        express_depart = next_express
        # Wait time at Chambers = when express arrives - when we arrive - buffer
        wait_time = max(0, express_depart - arrive_at_chambers - TRANSFER_BUFFER)
        # Total time = when express arrives + travel time on express
        # (express_depart already accounts for all waiting)
        transfer_total = express_depart + CHAMBERS_TO_PENN_ON_EXPRESS
        transfer_available = True
        if wait_time == 0:
            print(f"        ✓ Can catch {next_express}-minute train immediately (no wait!)")
        else:
            print(f"        ✓ Can catch {next_express}-minute train (wait: {wait_time} min at platform)")
    else:
        # Use next available even if we have to wait
        if sample_express_minutes:
            next_express = sample_express_minutes[0]
            express_depart = next_express
            wait_time = max(0, express_depart - arrive_at_chambers - TRANSFER_BUFFER)
            transfer_total = express_depart + wait_time + CHAMBERS_TO_PENN_ON_EXPRESS
            transfer_available = True
            print(f"        ⚠️  Must wait for {next_express}-minute train (wait: {wait_time} min)")
        else:
            transfer_total = None
            transfer_available = False
            print(f"        ❌ No express trains available")
    print()
    
    # Step 5: Calculate direct option
    direct_total = depart_time + SOUTH_FERRY_TO_CHAMBERS + CHAMBERS_TO_PENN_ON_1
    
    # Display results
    print("=" * 70)
    print("RESULTS")
    print("=" * 70)
    print()
    
    print("Option 1 (Direct - Stay on 1 train):")
    print(f"  ⏱️  Total time: {direct_total} minutes")
    print(f"     • Wait for 1 train: {depart_time} min")
    print(f"     • South Ferry → Chambers: {SOUTH_FERRY_TO_CHAMBERS} min")
    print(f"     • Chambers → Penn (local, 6 stops): {CHAMBERS_TO_PENN_ON_1} min")
    print()
    
    if transfer_available:
        print("Option 2 (Transfer to 2/3 express at Chambers):")
        print(f"  ⏱️  Total time: {transfer_total} minutes")
        print(f"     • Wait for 1 train: {depart_time} min")
        print(f"     • South Ferry → Chambers: {SOUTH_FERRY_TO_CHAMBERS} min")
        if wait_time > 0:
            print(f"     • Wait for 2/3 train: {wait_time} min")
        print(f"     • Transfer buffer: {TRANSFER_BUFFER} min")
        print(f"     • Chambers → Penn (express, 4 stops): {CHAMBERS_TO_PENN_ON_EXPRESS} min")
        print()
        
        print("=" * 70)
        if direct_total < transfer_total:
            saved = transfer_total - direct_total
            print(f"🏆 RECOMMENDATION: Option 1 (Direct) is faster by {saved} minutes")
            print(f"   Direct: {direct_total} min | Transfer: {transfer_total} min")
        elif transfer_total < direct_total:
            saved = direct_total - transfer_total
            print(f"🏆 RECOMMENDATION: Option 2 (Transfer) is faster by {saved} minutes")
            print(f"   Transfer: {transfer_total} min | Direct: {direct_total} min")
        else:
            print(f"🏆 RECOMMENDATION: Both options take the same time ({direct_total} min)")
        print("=" * 70)
    else:
        print("Option 2 (Transfer): Not available")
        print()
        print("=" * 70)
        print(f"🏆 RECOMMENDATION: Option 1 (Direct) - only option available")
        print(f"   Total time: {direct_total} minutes")
        print("=" * 70)

if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("DEMO: Testing different scenarios")
    print("=" * 70)
    print()
    
    # Scenario 1: Express arrives soon after reaching Chambers
    print("SCENARIO 1: Express train arrives soon")
    print("-" * 70)
    compare_routes_demo(sample_1_train_minutes=3, sample_express_minutes=[10, 15, 20])
    print("\n\n")
    
    # Scenario 2: Express arrives much later
    print("SCENARIO 2: Express train arrives later")
    print("-" * 70)
    compare_routes_demo(sample_1_train_minutes=2, sample_express_minutes=[15, 22, 28])
    print("\n\n")
    
    # Scenario 3: Express arrives just in time
    print("SCENARIO 3: Express train arrives just in time")
    print("-" * 70)
    compare_routes_demo(sample_1_train_minutes=5, sample_express_minutes=[13, 18, 25])
    print("\n\n")
    
    # Scenario 4: Express arrives right when we're ready (transfer wins!)
    print("SCENARIO 4: Express train arrives right when we're ready at Chambers (transfer wins!)")
    print("-" * 70)
    # If we arrive at Chambers at 10 min, need train at 12 min (10 + 2 buffer)
    # Express saves 2 min (6 local vs 4 express), so if it arrives at 12 min exactly, transfer wins!
    compare_routes_demo(sample_1_train_minutes=2, sample_express_minutes=[12, 18, 24])
    print()
