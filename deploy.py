#!/usr/bin/env python3
"""
MosPay Deployment Helper Script
This script helps prepare the application for deployment to Render.com
"""

import os
import secrets
import sys


def generate_secret_key():
    """Generate a secure secret key"""
    return secrets.token_urlsafe(32)


def check_requirements():
    """Check if all required files exist"""
    required_files = [
        "requirements.txt",
        "Procfile",
        "runtime.txt",
        "render.yaml",
        "app.py",
        "config.py",
    ]

    missing_files = []
    for file in required_files:
        if not os.path.exists(file):
            missing_files.append(file)

    if missing_files:
        print("❌ Missing required files:")
        for file in missing_files:
            print(f"   - {file}")
        return False

    print("✅ All required files present")
    return True


def generate_env_vars():
    """Generate environment variables for production"""
    print("\n🔐 Generated Environment Variables for Render:")
    print("=" * 50)
    print(f"SECRET_KEY={generate_secret_key()}")
    print(f"JWT_SECRET_KEY={generate_secret_key()}")
    print("FLASK_ENV=production")
    print("DATABASE_URL=<will be provided by Render PostgreSQL service>")
    print("=" * 50)
    print("\n📝 Copy these to your Render environment variables (except DATABASE_URL)")


def show_deployment_steps():
    """Show deployment steps"""
    print("\n🚀 Deployment Steps:")
    print("=" * 50)
    print("1. Push your code to GitHub: https://github.com/latomcore/mospay.git")
    print("2. Go to https://dashboard.render.com")
    print("3. Create a new Web Service")
    print("4. Connect your GitHub repository")
    print("5. Create a PostgreSQL database")
    print("6. Set environment variables (see above)")
    print("7. Deploy!")
    print("\n📖 For detailed instructions, see DEPLOYMENT.md")


def main():
    print("🎯 MosPay Deployment Helper")
    print("=" * 30)

    if not check_requirements():
        print("\n❌ Please ensure all required files are present before deploying")
        sys.exit(1)

    generate_env_vars()
    show_deployment_steps()

    print("\n✅ Ready for deployment!")
    print("🌐 Your app will be available at: https://mospay.onrender.com")
    print("📚 Documentation: https://mospay.onrender.com/docs")
    print("🔧 Admin Portal: https://mospay.onrender.com/admin")


if __name__ == "__main__":
    main()

