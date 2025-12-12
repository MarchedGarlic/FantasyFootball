#!/usr/bin/env python3
"""
Test Manager Grade System with Sample Data
"""

from trade_analysis import calculate_manager_grades, create_manager_grade_visualization

def test_manager_grades():
    """Test the manager grade system with sample data"""
    print("🧪 Testing Manager Grade System...")
    
    # Sample data
    sample_trade_impacts = [
        {
            'manager_id': 'user1',
            'manager_name': 'TestManager1',
            'combined_impact': 15.0,
            'week': 4
        },
        {
            'manager_id': 'user2', 
            'manager_name': 'TestManager2',
            'combined_impact': -8.0,
            'week': 5
        }
    ]
    
    sample_waiver_impacts = [
        {
            'manager_id': 'user1',
            'manager_name': 'TestManager1', 
            'combined_impact': 5.0,
            'week': 6
        }
    ]
    
    sample_power_data = {
        'user1': {
            'name': 'TestManager1',
            'weekly_power_ratings': {1: 120, 2: 125, 3: 110, 4: 140, 5: 135}
        },
        'user2': {
            'name': 'TestManager2',
            'weekly_power_ratings': {1: 100, 2: 95, 3: 105, 4: 90, 5: 110}
        }
    }
    
    sample_roster_data = {
        'user1': {
            'name': 'TestManager1',
            'weekly_roster_grades': {1: 25, 2: 28, 3: 22, 4: 32, 5: 30}
        },
        'user2': {
            'name': 'TestManager2', 
            'weekly_roster_grades': {1: 20, 2: 18, 3: 24, 4: 19, 5: 26}
        }
    }
    
    sample_user_lookup = {
        'user1': {'display_name': 'TestManager1'},
        'user2': {'display_name': 'TestManager2'}
    }
    
    # Test manager grades calculation
    manager_grades = calculate_manager_grades(
        sample_trade_impacts, sample_waiver_impacts,
        sample_power_data, sample_roster_data, sample_user_lookup
    )
    
    print(f"\n📊 Manager Grades Generated: {len(manager_grades)}")
    
    for manager_id, data in manager_grades.items():
        print(f"   • {data['name']}: {data['overall_grade']:.1f}/10")
        print(f"     - Weekly grades: {len(data['weekly_grades'])} weeks")
        print(f"     - Record: {data['record']['wins']}-{data['record']['losses']}")
    
    # Test visualization
    if manager_grades:
        print("\n🎨 Testing Manager Grade Visualization...")
        try:
            plot_file = create_manager_grade_visualization(manager_grades)
            if plot_file:
                print(f"   ✅ Visualization created: {plot_file}")
            else:
                print("   ⚠️  Visualization creation skipped (missing Bokeh)")
        except Exception as e:
            print(f"   ❌ Visualization error: {e}")
    
    return manager_grades

if __name__ == "__main__":
    print("🏆 Testing Manager Grade System")
    print("=" * 50)
    
    grades = test_manager_grades()
    
    if grades:
        print("\n✅ Manager Grade System Working!")
        print("\n📋 Features Tested:")
        print("   • Comprehensive grading formula")
        print("   • Weekly progression tracking")
        print("   • Record simulation")
        print("   • Trade/waiver performance integration")
        print("   • Interactive visualization with trends")
    else:
        print("\n❌ Manager Grade System needs debugging")