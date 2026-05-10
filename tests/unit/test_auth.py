import os
import sys
from unittest import mock
import pytest
from fastapi import HTTPException, status
from fastapi.security import HTTPBasicCredentials

# Ensure showcase_admin is in the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from showcase_admin.app.auth import verify_admin_credentials

def test_verify_credentials_disabled():
    # Mock auth disabled
    with mock.patch("showcase_admin.app.config.ADMIN_AUTHENTICATION_ENABLED", False):
        # Any mock credentials should pass
        credentials = HTTPBasicCredentials(username="bad-user", password="bad-password")
        assert verify_admin_credentials(credentials) is True

def test_verify_credentials_success():
    # Mock auth enabled and specific credentials
    with mock.patch("showcase_admin.app.config.ADMIN_AUTHENTICATION_ENABLED", True), \
         mock.patch("showcase_admin.app.config.ADMIN_USERNAME", "admin"), \
         mock.patch("showcase_admin.app.config.ADMIN_PASSWORD", "secret-pass"):
        
        credentials = HTTPBasicCredentials(username="admin", password="secret-pass")
        assert verify_admin_credentials(credentials) is True

def test_verify_credentials_failure():
    # Mock auth enabled and specific credentials
    with mock.patch("showcase_admin.app.config.ADMIN_AUTHENTICATION_ENABLED", True), \
         mock.patch("showcase_admin.app.config.ADMIN_USERNAME", "admin"), \
         mock.patch("showcase_admin.app.config.ADMIN_PASSWORD", "secret-pass"):
        
        credentials = HTTPBasicCredentials(username="admin", password="wrong-password")
        with pytest.raises(HTTPException) as exc_info:
            verify_admin_credentials(credentials)
            
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "WWW-Authenticate" in exc_info.value.headers
