from functools import wraps
from flask import request, jsonify, session, redirect, url_for, flash
from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity
import secrets
import string
from models import User, Client


def generate_app_id(length=8):
    """Generate a unique App ID"""
    characters = string.ascii_letters + string.digits
    return "".join(secrets.choice(characters) for _ in range(length))


def generate_api_credentials():
    """Generate API username and password"""
    username = f"api_{generate_app_id(6)}"
    password = generate_app_id(12)
    return username, password


def create_client_token(client_id, services):
    """Create a JWT token for a client with their services"""
    from flask_jwt_extended import create_access_token

    # Create a unique string identifier for the client
    client_identifier = f"client_{client_id}"

    # Store additional data in the token
    additional_claims = {
        "client_id": client_id,
        "services": [service.service.name for service in services],
        "type": "client",
    }

    return create_access_token(
        identity=client_identifier, additional_claims=additional_claims
    )


def validate_client_auth(username, password, appid):
    """Validate client credentials and return client if valid"""
    client = Client.query.filter_by(api_username=username, app_id=appid).first()

    if client and client.check_api_password(password):
        return client
    return None


def client_auth_required(f):
    """Decorator to require valid client authentication"""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get("Authorization")
        appid = request.headers.get("X-App-ID")

        if not auth_header or not appid:
            return jsonify({"error": "Missing Authorization header or App ID"}), 401

        if not auth_header.startswith("Basic "):
            return jsonify({"error": "Invalid Authorization header format"}), 401

        try:
            import base64

            credentials = base64.b64decode(auth_header[6:]).decode("utf-8")
            username, password = credentials.split(":", 1)

            client = validate_client_auth(username, password, appid)
            if not client:
                return jsonify({"error": "Invalid credentials"}), 401

            # Store client in request context for use in route
            request.client = client
            return f(*args, **kwargs)

        except Exception as e:
            return jsonify({"error": "Invalid credentials format"}), 401

    return decorated_function


def client_jwt_auth_required(f):
    """Decorator to require valid client authentication using JWT token"""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity

        try:
            verify_jwt_in_request()
            token_data = get_jwt_identity()

            # Verify this is a client token
            if not isinstance(token_data, dict) or token_data.get("type") != "client":
                return jsonify({"error": "Invalid token type"}), 401

            # Get client from database
            client = Client.query.get(token_data["client_id"])
            if not client or not client.is_active:
                return jsonify({"error": "Invalid or inactive client"}), 401

            # Store client in request context for use in route
            from flask import request

            request.client = client
            return f(*args, **kwargs)

        except Exception as e:
            return jsonify({"error": "Invalid or missing JWT token"}), 401

    return decorated_function


def admin_required(f):
    """Decorator to require admin authentication for web routes or JWT for API routes"""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check if this is a web request by looking at User-Agent and Accept headers
        user_agent = request.headers.get("User-Agent", "")
        accept_header = request.headers.get("Accept", "")

        # If User-Agent contains browser indicators or Accept contains HTML, treat as web request
        # Also check if it's a requests library (which indicates programmatic access)
        is_web_request = (
            "Mozilla" in user_agent
            or "Chrome" in user_agent
            or "Safari" in user_agent
            or "Firefox" in user_agent
            or "text/html" in accept_header
            or "application/xhtml+xml" in accept_header
            or "python-requests" in user_agent  # Handle requests library
        )

        if is_web_request:
            # Web route - use session authentication
            if "user_id" not in session:
                # For programmatic requests, return JSON error
                if "python-requests" in user_agent:
                    return jsonify({"error": "Please log in to access this page"}), 401
                # For browser requests, redirect to login
                flash("Please log in to access this page.", "error")
                return redirect(url_for("auth.login"))

            user = User.query.get(session["user_id"])
            if not user or user.role not in ["admin", "super_admin"]:
                # For programmatic requests, return JSON error
                if "python-requests" in user_agent:
                    return (
                        jsonify({"error": "Access denied. Admin privileges required."}),
                        403,
                    )
                # For browser requests, redirect to login
                flash("Access denied. Admin privileges required.", "error")
                return redirect(url_for("auth.login"))

            # Store user in request context for use in route
            request.user = user
            return f(*args, **kwargs)
        else:
            # API route - use JWT authentication
            try:
                verify_jwt_in_request()
                user_id = get_jwt_identity()
                user = User.query.get(user_id)

                if not user or user.role not in ["admin", "super_admin"]:
                    return jsonify({"error": "Admin privileges required"}), 403

                request.user = user
                return f(*args, **kwargs)
            except Exception:
                return jsonify({"error": "Invalid or missing JWT token"}), 401

    return decorated_function


def super_admin_required(f):
    """Decorator to require super admin authentication for web routes or JWT for API routes"""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check if this is a web request by looking at User-Agent and Accept headers
        user_agent = request.headers.get("User-Agent", "")
        accept_header = request.headers.get("Accept", "")

        # If User-Agent contains browser indicators or Accept contains HTML, treat as web request
        # Also check if it's a requests library (which indicates programmatic access)
        is_web_request = (
            "Mozilla" in user_agent
            or "Chrome" in user_agent
            or "Safari" in user_agent
            or "Firefox" in user_agent
            or "text/html" in accept_header
            or "application/xhtml+xml" in accept_header
            or "python-requests" in user_agent  # Handle requests library
        )

        if is_web_request:
            # Web route - use session authentication
            if "user_id" not in session:
                # For programmatic requests, return JSON error
                if "python-requests" in user_agent:
                    return jsonify({"error": "Please log in to access this page"}), 401
                # For browser requests, redirect to login
                flash("Access denied. Super admin privileges required.", "error")
                return redirect(url_for("auth.login"))

            user = User.query.get(session["user_id"])
            if not user or user.role != "super_admin":
                # For programmatic requests, return JSON error
                if "python-requests" in user_agent:
                    return (
                        jsonify(
                            {"error": "Access denied. Super admin privileges required."}
                        ),
                        403,
                    )
                # For browser requests, redirect to login
                flash("Access denied. Super admin privileges required.", "error")
                return redirect(url_for("auth.login"))

            # Store user in request context for use in route
            request.user = user
            return f(*args, **kwargs)
        else:
            # API route - use JWT authentication
            try:
                verify_jwt_in_request()
                user_id = get_jwt_identity()
                user = User.query.get(user_id)

                if not user or user.role != "super_admin":
                    return jsonify({"error": "Super admin privileges required"}), 403

                request.user = user
                return f(*args, **kwargs)
            except Exception:
                return jsonify({"error": "Invalid or missing JWT token"}), 401

    return decorated_function
