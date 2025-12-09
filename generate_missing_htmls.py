#!/usr/bin/env python3
"""
Generate the missing HTML files for roster grades and manager grades
"""

def create_roster_grade_html():
    """Create roster grade HTML with sample data"""
    try:
        # Create sample roster grade data
        sample_roster_data = {
            '1127729098148655104': {
                'name': 'joeyscott31',
                'weekly_grades': {i: 30 + (i % 4) for i in range(1, 15)},
                'latest_grade': 33.7
            },
            '858068603554111488': {
                'name': 'Tcdun', 
                'weekly_grades': {i: 28 + (i % 3) for i in range(1, 15)},
                'latest_grade': 29.0
            },
            '993314024194396160': {
                'name': 'cmoney2137',
                'weekly_grades': {i: 31 + (i % 2) for i in range(1, 15)},
                'latest_grade': 32.5
            },
            '1260463320503169024': {
                'name': 'Shockley5',
                'weekly_grades': {i: 27 + (i % 5) for i in range(1, 15)},
                'latest_grade': 28.0
            },
            '1260463530457452544': {
                'name': 'Spillywilly69',
                'weekly_grades': {i: 29 + (i % 4) for i in range(1, 15)},
                'latest_grade': 30.5
            },
            '694022020266033152': {
                'name': 'coletheman88',
                'weekly_grades': {i: 28 + (i % 3) for i in range(1, 15)},
                'latest_grade': 29.5
            }
        }
        
        from visualizations import create_roster_grade_plot
        create_roster_grade_plot(sample_roster_data)
        print("✅ Roster grade HTML created successfully")
        
    except Exception as e:
        print(f"❌ Error creating roster grade HTML: {e}")

def create_manager_grade_html():
    """Create manager grade HTML with sample data"""
    try:
        # Create sample manager grade data
        sample_manager_data = {
            '1127729098148655104': {
                'name': 'joeyscott31',
                'weekly_grades': {str(i): 4.4 + (i % 3) * 0.2 for i in range(1, 15)},
                'overall_grade': 4.5,
                'trade_performance': 4.0,
                'waiver_performance': 4.5,
                'lineup_performance': 4.8
            },
            '858068603554111488': {
                'name': 'Tcdun',
                'weekly_grades': {str(i): 3.8 + (i % 4) * 0.15 for i in range(1, 15)},
                'overall_grade': 3.9,
                'trade_performance': 3.5,
                'waiver_performance': 4.0,
                'lineup_performance': 4.2
            },
            '993314024194396160': {
                'name': 'cmoney2137',
                'weekly_grades': {str(i): 3.7 + (i % 2) * 0.25 for i in range(1, 15)},
                'overall_grade': 3.8,
                'trade_performance': 3.9,
                'waiver_performance': 3.8,
                'lineup_performance': 3.7
            },
            '1260463320503169024': {
                'name': 'Shockley5',
                'weekly_grades': {str(i): 3.6 + (i % 5) * 0.18 for i in range(1, 15)},
                'overall_grade': 3.8,
                'trade_performance': 4.2,
                'waiver_performance': 3.5,
                'lineup_performance': 3.7
            },
            '1260463530457452544': {
                'name': 'Spillywilly69',
                'weekly_grades': {str(i): 3.4 + (i % 3) * 0.2 for i in range(1, 15)},
                'overall_grade': 3.5,
                'trade_performance': 3.0,
                'waiver_performance': 3.8,
                'lineup_performance': 3.7
            },
            '694022020266033152': {
                'name': 'coletheman88',
                'weekly_grades': {str(i): 4.3 + (i % 4) * 0.15 for i in range(1, 15)},
                'overall_grade': 4.4,
                'trade_performance': 4.1,
                'waiver_performance': 4.5,
                'lineup_performance': 4.6
            }
        }
        
        from trade_analysis import create_manager_grade_visualization
        create_manager_grade_visualization(sample_manager_data)
        print("✅ Manager grade HTML created successfully")
        
    except Exception as e:
        print(f"❌ Error creating manager grade HTML: {e}")

if __name__ == "__main__":
    print("🔧 Generating missing HTML files...")
    print("\n📊 Creating Roster Grade visualization...")
    create_roster_grade_html()
    
    print("\n👥 Creating Manager Grade visualization...")
    create_manager_grade_html()
    
    print("\n🎉 Done! Check for the new HTML files.")