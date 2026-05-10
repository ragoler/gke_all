import os
import sys

# Ensure workspace directory is in the Python search path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Force MOCK mode during tests for security
os.environ["MODE"] = "MOCK"
os.environ["ADMIN_AUTHENTICATION_ENABLED"] = "TRUE"
os.environ["ADMIN_USERNAME"] = "test-admin"
os.environ["ADMIN_PASSWORD"] = "test-pass"
