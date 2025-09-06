#!/usr/bin/env python3
"""
Script to create the new analytics and reporting tables
Run this script to add the new tables to your database
"""

import os
import sys
from datetime import datetime

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def create_analytics_tables():
    """Create the new analytics and reporting tables"""
    try:
        # Import after setting up the path
        from app import create_app
        from models import db
        
        app = create_app()
        
        with app.app_context():
            print("Creating analytics and reporting tables...")
            
            # Create all tables
            db.create_all()
            
            print("✅ Successfully created all tables!")
            print("New tables created:")
            print("  - report_templates")
            print("  - scheduled_reports") 
            print("  - report_executions")
            
            # Test the tables
            from models import ReportTemplate, ScheduledReport, ReportExecution
            
            # Check if tables exist by querying them
            template_count = ReportTemplate.query.count()
            scheduled_count = ScheduledReport.query.count()
            execution_count = ReportExecution.query.count()
            
            print(f"\nTable verification:")
            print(f"  - report_templates: {template_count} records")
            print(f"  - scheduled_reports: {scheduled_count} records")
            print(f"  - report_executions: {execution_count} records")
            
            print("\n🎉 Analytics tables are ready!")
            print("You can now access the analytics dashboard and reporting features.")
            
    except Exception as e:
        print(f"❌ Error creating tables: {e}")
        print("\nTroubleshooting:")
        print("1. Make sure your database is running")
        print("2. Check your DATABASE_URL environment variable")
        print("3. Ensure all dependencies are installed")
        return False
    
    return True

if __name__ == "__main__":
    print("MosPay Analytics Tables Creator")
    print("=" * 40)
    
    success = create_analytics_tables()
    
    if success:
        print("\n✅ Setup complete! You can now use the analytics features.")
    else:
        print("\n❌ Setup failed. Please check the error messages above.")
        sys.exit(1)
