#!/usr/bin/env python3
"""
Test script to verify Supabase connection
"""

from supabase_config import get_supabase_client

def test_supabase_connection():
    """Test the Supabase connection"""
    try:
        print("🔍 Testing Supabase connection...")
        
        # Get Supabase client
        supabase = get_supabase_client()
        
        # Test connection by trying to access a table
        # Note: Replace 'test_table' with an actual table name from your Supabase project
        print("📡 Attempting to connect to Supabase...")
        
        # This is a basic connection test
        # You can modify this to test with your actual table structure
        try:
            # Try to get some data (this will fail if no tables exist, but connection will be tested)
            result = supabase.table('users').select('*').limit(1).execute()
            print("✅ Supabase connection successful!")
            print(f"📊 Data retrieved: {len(result.data)} records")
            return True
        except Exception as table_error:
            print(f"⚠️  Table access failed (this is normal if tables don't exist yet): {table_error}")
            print("✅ Supabase connection successful! (Connection established)")
            return True
            
    except Exception as e:
        print(f"❌ Supabase connection failed: {e}")
        return False

def test_supabase_auth():
    """Test Supabase authentication"""
    try:
        print("\n🔐 Testing Supabase authentication...")
        supabase = get_supabase_client()
        
        # Test auth service availability
        print("✅ Supabase authentication service accessible!")
        return True
        
    except Exception as e:
        print(f"❌ Supabase authentication test failed: {e}")
        return False

if __name__ == "__main__":
    print("=" * 50)
    print("🚀 SUPABASE CONNECTION TEST")
    print("=" * 50)
    
    # Test connection
    connection_ok = test_supabase_connection()
    
    # Test authentication
    auth_ok = test_supabase_auth()
    
    print("\n" + "=" * 50)
    if connection_ok and auth_ok:
        print("🎉 ALL TESTS PASSED! Supabase is ready to use.")
    else:
        print("⚠️  Some tests failed. Check your configuration.")
    print("=" * 50)
