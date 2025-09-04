#!/usr/bin/env python3
"""
Startup script for MosPay
This script initializes the application and starts the server
"""

import os
import sys
from app import create_app


def main():
    """Main startup function"""
    print("=" * 60)
    print("MosPay - Starting Up")
    print("=" * 60)

    try:
        # Create the Flask application
        print("Creating Flask application...")
        app = create_app()

        # Get configuration
        debug_mode = app.config.get("DEBUG", False)
        host = app.config.get("HOST", "0.0.0.0")
        port = app.config.get("PORT", 5000)

        print(f"Configuration:")
        print(f"  Debug Mode: {debug_mode}")
        print(f"  Host: {host}")
        print(f"  Port: {port}")
        print(
            f"  Database: {app.config.get('SQLALCHEMY_DATABASE_URI', 'Not configured')[:50]}..."
        )

        print("\nStarting server...")
        print(f"Admin Portal: http://{host}:{port}")
        print(f"API Base: http://{host}:{port}/api/v1")
        print(f"Health Check: http://{host}:{port}/health")
        print("\nPress Ctrl+C to stop the server")
        print("=" * 60)

        # Start the application
        app.run(host=host, port=port, debug=debug_mode)

    except Exception as e:
        print(f"Error starting application: {e}")
        print("\nPlease check:")
        print("1. Database connection")
        print("2. Environment variables")
        print("3. Dependencies installation")
        sys.exit(1)


if __name__ == "__main__":
    main()
