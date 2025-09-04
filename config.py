import os
from datetime import timedelta


class Config:
    SECRET_KEY = (
        os.environ.get("SECRET_KEY") or "your-secret-key-here-change-in-production"
    )

    # Database configuration
    SQLALCHEMY_DATABASE_URI = (
        os.environ.get("DATABASE_URL")
        or "postgresql://aretechltd_db_user:QhJPDUdbBZeG5kjrl6nXjJUHdko9dSYJ@dpg-d2rkgtripnbc73d5g460-a.frankfurt-postgres.render.com:5432/aretechltd_db"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Database connection pooling and retry settings
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_size": 10,
        "pool_timeout": 20,
        "pool_recycle": 3600,  # Recycle connections every hour
        "pool_pre_ping": True,  # Verify connection before use
        "max_overflow": 20,
        "connect_args": {"connect_timeout": 10, "application_name": "mospay_admin"},
    }

    # JWT configuration
    JWT_SECRET_KEY = (
        os.environ.get("JWT_SECRET_KEY") or "jwt-secret-key-change-in-production"
    )
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=24)
    JWT_TOKEN_LOCATION = ["headers"]
    JWT_HEADER_NAME = "Authorization"
    JWT_HEADER_TYPE = "Bearer"

    # API configuration
    API_TITLE = "MosPay"
    API_VERSION = "v1"

    # Microservices configuration
    MICROSERVICES_NETWORK = "http://microservices:8080"

    # Security
    BCRYPT_LOG_ROUNDS = 12
