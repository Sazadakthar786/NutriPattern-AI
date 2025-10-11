import os
from supabase import create_client, Client
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Supabase configuration from environment variables
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_ANON_KEY = os.getenv('SUPABASE_ANON_KEY')

# Validate that environment variables are set
if not SUPABASE_URL or not SUPABASE_ANON_KEY:
    raise ValueError(
        "Supabase credentials not found! Please set SUPABASE_URL and SUPABASE_ANON_KEY environment variables.\n"
        "Create a .env file with your Supabase credentials. See env_template.txt for reference."
    )

# Create Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

def get_supabase_client():
    """Get the Supabase client instance"""
    return supabase
