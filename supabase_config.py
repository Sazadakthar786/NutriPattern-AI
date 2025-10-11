import os
from supabase import create_client, Client

# Supabase configuration
SUPABASE_URL = "https://qvswoxihuzbjexnuaxdl.supabase.co"
SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InF2c3dveGlodXpiamV4bnVheGRsIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjAxMjA3NTUsImV4cCI6MjA3NTY5Njc1NX0.8WRFFX6LkqA2h8ZQ7Z_aF_wRa4YTXaed187tkwCUJZM"

# Create Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

def get_supabase_client():
    """Get the Supabase client instance"""
    return supabase
