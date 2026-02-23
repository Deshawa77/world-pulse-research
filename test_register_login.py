import requests

# Test 1: Register a new user
print("=== Testing Registration ===")
register_response = requests.post(
    "http://localhost:8000/auth/register",
    json={
        "name": "Test User",
        "email": "testuser123@example.com",
        "password": "testpass123",
        "role": "researcher",
        "organization": "Test Org"
    }
)
print(f"Register Status: {register_response.status_code}")
print(f"Register Response: {register_response.json()}")

# Test 2: Login with the new user
print("\n=== Testing Login ===")
login_response = requests.post(
    "http://localhost:8000/auth/login",
    json={
        "email": "testuser123@example.com",
        "password": "testpass123"
    }
)
print(f"Login Status: {login_response.status_code}")
print(f"Login Response: {login_response.json()}")
