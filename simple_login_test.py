#!/usr/bin/env python3
"""
Simple login test to debug the authentication issue
"""

import requests

# Configuration
BASE_URL = "http://localhost:5000"
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"


def test_login():
    """Test login and show detailed response"""
    print("=== Testing Login ===")

    # Create session
    session = requests.Session()

    # Get login page
    print("1. Getting login page...")
    login_page_response = session.get(f"{BASE_URL}/auth/login")
    print(f"   Status: {login_page_response.status_code}")
    print(f"   Content length: {len(login_page_response.text)}")

    if "Admin Login" in login_page_response.text:
        print("   ✅ Login page contains 'Admin Login'")
    else:
        print("   ❌ Login page doesn't contain 'Admin Login'")

    # Try to login
    print("\n2. Attempting login...")
    login_data = {"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD}

    login_response = session.post(f"{BASE_URL}/auth/login", data=login_data)
    print(f"   Status: {login_response.status_code}")
    print(f"   Headers: {dict(login_response.headers)}")

    if login_response.status_code == 302:
        print("   ✅ Login successful - redirected")
        print(f"   Redirect location: {login_response.headers.get('Location', 'None')}")
    elif login_response.status_code == 200:
        print("   ⚠️  Login returned 200 - might have failed")
        if "Invalid username or password" in login_response.text:
            print("   ❌ Login failed - invalid credentials")
        elif "Login successful" in login_response.text:
            print("   ✅ Login successful message found")
        else:
            print("   ❓ Unknown response - checking content...")
            print(f"   Content preview: {login_response.text[:200]}...")
    else:
        print(f"   ❌ Unexpected status: {login_response.status_code}")

    # Check if we can access admin dashboard
    print("\n3. Testing admin dashboard access...")
    dashboard_response = session.get(f"{BASE_URL}/admin/dashboard")
    print(f"   Dashboard status: {dashboard_response.status_code}")

    if dashboard_response.status_code == 200:
        print("   ✅ Dashboard accessible")
        if "Dashboard" in dashboard_response.text:
            print("   ✅ Dashboard content found")
        else:
            print("   ❌ Dashboard content not found")
    elif dashboard_response.status_code == 302:
        print("   ⚠️  Dashboard redirects - might need login")
        print(
            f"   Redirect location: {dashboard_response.headers.get('Location', 'None')}"
        )
    else:
        print(f"   ❌ Dashboard access failed: {dashboard_response.status_code}")


if __name__ == "__main__":
    test_login()

