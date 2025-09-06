from flask import Flask, render_template, jsonify, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager
from flask_bcrypt import Bcrypt
from flask_cors import CORS
from flask_login import LoginManager
from config import Config
from models import db, User, Client, Service, ServiceField, ClientService
from auth import generate_app_id, generate_api_credentials
import os


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Production configuration
    if os.environ.get("FLASK_ENV") == "production":
        app.config["DEBUG"] = False
        app.config["TESTING"] = False
        # Production database configuration
        if os.environ.get("DATABASE_URL"):
            raw_db_url = os.environ.get("DATABASE_URL")
            # Ensure psycopg v3 driver is used
            app.config["SQLALCHEMY_DATABASE_URI"] = raw_db_url.replace(
                "postgresql://", "postgresql+psycopg://"
            )
        # Production secret keys
        if os.environ.get("SECRET_KEY"):
            app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY")
        if os.environ.get("JWT_SECRET_KEY"):
            app.config["JWT_SECRET_KEY"] = os.environ.get("JWT_SECRET_KEY")

    # Initialize extensions
    db.init_app(app)
    jwt = JWTManager(app)
    bcrypt = Bcrypt(app)
    CORS(app)
    
    # Initialize Flask-Login
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'info'
    
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Configure JWT settings
    app.config["JWT_TOKEN_LOCATION"] = ["headers"]
    app.config["JWT_HEADER_NAME"] = "Authorization"
    app.config["JWT_HEADER_TYPE"] = "Bearer"

    # Register blueprints
    from api_routes import api
    from admin_routes import admin
    from auth_routes import auth_bp
    from client_routes import client

    app.register_blueprint(api, url_prefix="/api/v1")
    app.register_blueprint(admin, url_prefix="/admin")
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(client, url_prefix="/client")

    # Database connection error handler
    @app.errorhandler(500)
    def internal_error(error):
        # Check if it's a database connection error
        if hasattr(error, "description") and "server closed the connection" in str(
            error.description
        ):
            return (
                render_template(
                    "500.html", error="Database connection lost. Please try again."
                ),
                500,
            )
        return (
            render_template("500.html", error="An internal server error occurred."),
            500,
        )

    # Create database tables
    with app.app_context():
        try:
            # Test database connection first
            from sqlalchemy import text
            db.session.execute(text("SELECT 1"))
            print("Database connection successful")
            
            # Create tables
            db.create_all()
            print("Database tables created successfully")
        except Exception as e:
            print(f"Database error: {e}")
            print("This might be due to connection issues or missing environment variables.")
            # Don't exit in production, let the app start and handle errors gracefully
            if os.environ.get("FLASK_ENV") != "production":
                raise

        # Create default super admin user if it doesn't exist
        if not User.query.filter_by(role="super_admin").first():
            super_admin = User(
                username="admin", email="admin@mospay.com", role="super_admin"
            )
            super_admin.set_password("admin123")
            db.session.add(super_admin)

            # Create default services
            default_services = [
                {
                    "name": "mtnmomorwa",
                    "display_name": "MTN MoMo Rwanda",
                    "description": "MTN Mobile Money Rwanda service",
                    "service_url": "http://mtnmomorwa:8080/provider/api",
                },
                {
                    "name": "airtelmoney",
                    "display_name": "Airtel Money",
                    "description": "Airtel Money service",
                    "service_url": "http://airtelmoney:8080/provider/api",
                },
                {
                    "name": "mpesa",
                    "display_name": "M-Pesa",
                    "description": "M-Pesa mobile money service",
                    "service_url": "http://mpesa:8080/provider/api",
                },
            ]

            for service_data in default_services:
                if not Service.query.filter_by(name=service_data["name"]).first():
                    service = Service(**service_data)
                    db.session.add(service)
                    db.session.flush()  # Get the service ID

                    # Add default service fields
                    default_fields = [
                        ("f000", "App ID", "string", True, "Client application ID"),
                        ("f001", "Service Name", "string", True, "Name of the service"),
                        (
                            "f002",
                            "Service Route",
                            "string",
                            True,
                            "Route for the service",
                        ),
                        ("f003", "App ID", "string", True, "Client application ID"),
                        ("f004", "Amount", "number", True, "Transaction amount"),
                        (
                            "f005",
                            "Mobile Number",
                            "string",
                            True,
                            "Customer mobile number",
                        ),
                        ("f006", "Username", "string", True, "Customer username"),
                        (
                            "f007",
                            "Encrypted Password",
                            "string",
                            True,
                            "Encrypted password",
                        ),
                        ("f008", "Password", "string", True, "Password"),
                        ("f009", "Device ID", "string", True, "Device identifier"),
                        (
                            "f010",
                            "Unique ID",
                            "string",
                            True,
                            "Unique transaction identifier",
                        ),
                    ]

                    for (
                        field_code,
                        field_name,
                        field_type,
                        is_required,
                        description,
                    ) in default_fields:
                        service_field = ServiceField(
                            service_id=service.id,
                            field_code=field_code,
                            field_name=field_name,
                            field_type=field_type,
                            is_required=is_required,
                            description=description,
                        )
                        db.session.add(service_field)

            db.session.commit()
            print("Default super admin user and services created!")

    # Default route
    @app.route("/")
    def index():
        return redirect(url_for("auth.login"))

    # Health check
    @app.route("/health")
    def health():
        try:
            # Test database connection
            from sqlalchemy import text

            db.session.execute(text("SELECT 1"))
            db_status = "connected"
        except Exception as e:
            db_status = f"error: {str(e)[:100]}"

        return jsonify(
            {
                "status": "healthy",
                "service": "MosPay",
                "version": "1.0.0",
                "database": db_status,
            }
        )

    # Documentation page
    @app.route("/docs")
    def docs():
        return render_template("docs.html")

    # Error handlers
    @app.errorhandler(404)
    def not_found_error(error):
        return render_template("404.html"), 404

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        return render_template("500.html"), 500

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
