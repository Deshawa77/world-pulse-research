import requests
import time

# Generate unique email using timestamp
timestamp = int(time.time())
email = f"testuser_{timestamp}@example.com"

# Test 1: Register a new user
print(f"=== Testing Registration with {email} ===")
register_response = requests.post(
    "http://localhost:8000/auth/register",
    json={
        "name": "Test User",
        "email": email,
        "password": "testpass123",
        "role": "researcher",
        "organization": "Test Org"
    }
)
print(f"Register Status: {register_response.status_code}")
print(f"Register Response: {register_response.json()}")

# Test 2: Login with the new user
print(f"\n=== Testing Login with {email} ===")
login_response = requests.post(
    "http://localhost:8000/auth/login",
    json={
        "email": email,
        "password": "testpass123"
    }
)
print(f"Login Status: {login_response.status_code}")
print(f"Login Response: {login_response.json()}")
