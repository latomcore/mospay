#!/usr/bin/env python3
"""
Migration script to add client portal authentication fields
"""

import os
import sys
from sqlalchemy import text

# Add the current directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from models import db

def migrate_client_portal():
    """Add client portal authentication fields to the clients table"""
    
    app = create_app()
    
    with app.app_context():
        try:
            print("🔄 Starting client portal migration...")
            
            # Check if columns already exist
            result = db.session.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'clients' 
                AND column_name IN ('portal_password_hash', 'last_login', 'login_attempts', 'account_locked', 'locked_until')
            """))
            
            existing_columns = [row[0] for row in result.fetchall()]
            print(f"📋 Existing columns: {existing_columns}")
            
            # Add missing columns
            columns_to_add = [
                ("portal_password_hash", "VARCHAR(255)"),
                ("last_login", "TIMESTAMP"),
                ("login_attempts", "INTEGER DEFAULT 0"),
                ("account_locked", "BOOLEAN DEFAULT FALSE"),
                ("locked_until", "TIMESTAMP")
            ]
            
            for column_name, column_type in columns_to_add:
                if column_name not in existing_columns:
                    try:
                        sql = f"ALTER TABLE clients ADD COLUMN {column_name} {column_type}"
                        print(f"🔧 Adding column: {column_name}")
                        db.session.execute(text(sql))
                        db.session.commit()
                        print(f"✅ Successfully added column: {column_name}")
                    except Exception as e:
                        print(f"❌ Error adding column {column_name}: {str(e)}")
                        db.session.rollback()
                else:
                    print(f"⏭️  Column {column_name} already exists, skipping...")
            
            # Verify the migration
            result = db.session.execute(text("""
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns 
                WHERE table_name = 'clients' 
                AND column_name IN ('portal_password_hash', 'last_login', 'login_attempts', 'account_locked', 'locked_until')
                ORDER BY column_name
            """))
            
            print("\n📊 Migration verification:")
            print("Column Name | Data Type | Nullable | Default")
            print("-" * 50)
            for row in result.fetchall():
                print(f"{row[0]:<20} | {row[1]:<10} | {row[2]:<8} | {row[3] or 'None'}")
            
            print("\n🎉 Client portal migration completed successfully!")
            
        except Exception as e:
            print(f"❌ Migration failed: {str(e)}")
            db.session.rollback()
            return False
        
        return True

if __name__ == "__main__":
    success = migrate_client_portal()
    if success:
        print("\n✅ Migration completed successfully!")
        print("🚀 Client portal is now ready to use!")
    else:
        print("\n❌ Migration failed!")
        sys.exit(1)
