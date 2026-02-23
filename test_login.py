import requests

# Test login
response = requests.post(
    "http://localhost:8000/auth/login",
    json={"email": "admin@wp.com", "password": "admin123"}
)

print(f"Status: {response.status_code}")
print(f"Response: {response.json()}")
