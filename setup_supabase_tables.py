#!/usr/bin/env python3
"""
Supabase Table Creation Script
This script helps you create the necessary tables in your Supabase project.
Run this script to set up the database schema.
"""

from supabase_config import get_supabase_client

def create_tables():
    """Create necessary tables in Supabase"""
    supabase = get_supabase_client()
    
    print("🚀 Creating Supabase tables...")
    
    # Note: In Supabase, tables are typically created via SQL in the dashboard
    # This script provides the SQL commands you need to run
    
    sql_commands = [
        """
        -- Users table
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(50) UNIQUE NOT NULL,
            patient_id VARCHAR(20) UNIQUE NOT NULL,
            age INTEGER NOT NULL,
            gender VARCHAR(10) NOT NULL,
            height DECIMAL(5,2) NOT NULL,
            weight DECIMAL(5,2) NOT NULL,
            role VARCHAR(20) DEFAULT 'user',
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );
        """,
        """
        -- Health reports table
        CREATE TABLE IF NOT EXISTS health_reports (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            filename VARCHAR(255) NOT NULL,
            extracted_text TEXT,
            extracted_values JSONB,
            analysis_results JSONB,
            diet_plan JSONB,
            comment TEXT,
            comment_timestamp TIMESTAMP WITH TIME ZONE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );
        """,
        """
        -- Messages table
        CREATE TABLE IF NOT EXISTS messages (
            id SERIAL PRIMARY KEY,
            sender_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            recipient_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            subject VARCHAR(255) NOT NULL,
            content TEXT NOT NULL,
            is_read BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );
        """,
        """
        -- Chat history table
        CREATE TABLE IF NOT EXISTS chat_history (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            message TEXT NOT NULL,
            response TEXT NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );
        """
    ]
    
    print("\n📋 SQL Commands to run in your Supabase SQL Editor:")
    print("=" * 60)
    
    for i, sql in enumerate(sql_commands, 1):
        print(f"\n-- Command {i}:")
        print(sql.strip())
    
    print("\n" + "=" * 60)
    print("📝 Instructions:")
    print("1. Go to your Supabase dashboard")
    print("2. Navigate to SQL Editor")
    print("3. Copy and paste each SQL command above")
    print("4. Run each command to create the tables")
    print("5. Verify tables are created in the Table Editor")
    
    # Test if tables exist
    print("\n🔍 Testing table existence...")
    tables_to_test = ['users', 'health_reports', 'messages', 'chat_history']
    
    for table in tables_to_test:
        try:
            result = supabase.table(table).select('*').limit(1).execute()
            print(f"✅ Table '{table}' exists and is accessible")
        except Exception as e:
            print(f"❌ Table '{table}' not found or not accessible: {e}")

if __name__ == "__main__":
    print("=" * 60)
    print("🗄️  SUPABASE TABLE SETUP")
    print("=" * 60)
    create_tables()
    print("\n🎉 Setup complete!")
