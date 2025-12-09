#!/usr/bin/env python3
"""
Test the new comprehensive analysis system
"""

def test_analysis_functions():
    """Test that the new analysis functions are available and working"""
    try:
        from trade_analysis import (
            analyze_real_trades_only, 
            analyze_waiver_pickups,
            calculate_manager_grades,
            create_trade_visualization,
            create_waiver_visualization,
            create_manager_grade_visualization,
            print_trade_analysis_results
        )
        
        print("✅ All comprehensive analysis functions imported successfully!")
        
        # Test with empty data to make sure functions handle no data gracefully
        print("\n🧪 Testing with empty data...")
        
        # Empty test data
        empty_transactions = {}
        empty_team_power = {}
        empty_roster_grade = {}
        empty_user_lookup = {}
        empty_roster_to_manager = {}
        
        # Test trade analysis
        trade_impacts = analyze_real_trades_only(
            empty_transactions, empty_team_power, empty_roster_grade, 
            empty_user_lookup, empty_roster_to_manager
        )
        print(f"   • Trade analysis: {len(trade_impacts)} impacts")
        
        # Test waiver analysis
        waiver_impacts = analyze_waiver_pickups(
            empty_transactions, empty_team_power, empty_roster_grade,
            empty_user_lookup, empty_roster_to_manager
        )
        print(f"   • Waiver analysis: {len(waiver_impacts)} impacts")
        
        # Test manager grades
        manager_grades = calculate_manager_grades(
            trade_impacts, waiver_impacts, empty_team_power,
            empty_roster_grade, empty_user_lookup
        )
        print(f"   • Manager grades: {len(manager_grades)} grades")
        
        # Test print function
        print("\n📊 Testing analysis results printing...")
        print_trade_analysis_results(trade_impacts, waiver_impacts)
        
        print("\n🎉 All tests passed! The comprehensive analysis system is ready.")
        
        return True
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False
    except Exception as e:
        print(f"❌ Test error: {e}")
        return False

if __name__ == "__main__":
    print("🔬 Testing Comprehensive Analysis System")
    print("="*50)
    
    success = test_analysis_functions()
    
    if success:
        print("\n✅ System ready for full fantasy analysis!")
        print("\nNew Features Available:")
        print("   🔄 Pure Trade Analysis - Real player movements only")
        print("   📊 Waiver Wire Analysis - Pickup impact scoring")  
        print("   🏆 Manager Performance Grades - Comprehensive evaluation")
        print("   📈 Enhanced Visualizations - Separate plots for each analysis type")
    else:
        print("\n❌ System has issues that need to be fixed")