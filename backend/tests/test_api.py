import pytest
from fastapi.testclient import TestClient
from app.main import app

# We initialize TestClient inside the tests so we don't trigger the lifespan startup outside of a test context if we don't want to.
client = TestClient(app)

def test_health_check():
    """Test that the application boots up and the health check endpoint works."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_protected_routes_require_auth():
    """Test that the core pipeline API endpoints are protected by authentication."""
    # Attempting to patch a draft without a valid Bearer token should fail with 401 Unauthorized
    response = client.patch("/api/v1/trends/some-id/draft/0", json={"text": "test"})
    assert response.status_code == 401
    assert "Missing Authorization header" in response.text
