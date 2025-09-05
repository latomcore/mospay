from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from datetime import datetime
import uuid

db = SQLAlchemy()
bcrypt = Bcrypt()


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default="admin")  # admin, super_admin
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def set_password(self, password):
        self.password_hash = bcrypt.generate_password_hash(password).decode("utf-8")

    def check_password(self, password):
        return bcrypt.check_password_hash(self.password_hash, password)


class Client(db.Model):
    __tablename__ = "clients"

    id = db.Column(db.Integer, primary_key=True)
    app_id = db.Column(db.String(100), unique=True, nullable=False)
    company_name = db.Column(db.String(200), nullable=False)
    contact_person = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(200), nullable=False)
    phone = db.Column(db.String(50), nullable=False)
    address = db.Column(db.Text, nullable=False)
    api_username = db.Column(db.String(100), unique=True, nullable=False)
    api_password_hash = db.Column(db.String(255), nullable=False)
    # New: optional callback URL for client notifications
    callback_url = db.Column(db.String(500))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    services = db.relationship(
        "ClientService",
        backref="client",
        lazy=True,
        primaryjoin="and_(Client.id==ClientService.client_id, ClientService.is_active==True)",
    )

    def set_api_password(self, password):
        self.api_password_hash = bcrypt.generate_password_hash(password).decode("utf-8")

    def check_api_password(self, password):
        return bcrypt.check_password_hash(self.api_password_hash, password)


class Service(db.Model):
    __tablename__ = "services"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    display_name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    service_url = db.Column(db.String(500), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    client_services = db.relationship("ClientService", backref="service", lazy=True)
    service_fields = db.relationship("ServiceField", backref="service", lazy=True)


class ServiceField(db.Model):
    __tablename__ = "service_fields"

    id = db.Column(db.Integer, primary_key=True)
    service_id = db.Column(db.Integer, db.ForeignKey("services.id"), nullable=False)
    field_code = db.Column(db.String(20), nullable=False)  # f000, f001, etc.
    field_name = db.Column(db.String(100), nullable=False)
    field_type = db.Column(db.String(50), nullable=False)  # string, number, email, etc.
    is_required = db.Column(db.Boolean, default=True)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class ClientService(db.Model):
    __tablename__ = "client_services"

    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey("clients.id"), nullable=False)
    service_id = db.Column(db.Integer, db.ForeignKey("services.id"), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class Transaction(db.Model):
    __tablename__ = "transactions"

    id = db.Column(db.Integer, primary_key=True)
    unique_id = db.Column(db.String(100), unique=True, nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey("clients.id"), nullable=False)
    service_id = db.Column(db.Integer, db.ForeignKey("services.id"), nullable=False)
    status = db.Column(
        db.String(50), default="pending"
    )  # pending, processing, completed, failed
    amount = db.Column(db.Numeric(10, 2))
    mobile_number = db.Column(db.String(50))
    device_id = db.Column(db.String(100))
    request_payload = db.Column(db.JSON)
    response_payload = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    client = db.relationship("Client", backref="transactions")
    service = db.relationship("Service", backref="transactions")


class ApiLog(db.Model):
    __tablename__ = "api_logs"

    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey("clients.id"), nullable=False)
    endpoint = db.Column(db.String(200), nullable=False)
    method = db.Column(db.String(10), nullable=False)
    request_data = db.Column(db.JSON)
    response_data = db.Column(db.JSON)
    status_code = db.Column(db.Integer)
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    client = db.relationship("Client", backref="api_logs")


class Alert(db.Model):
    __tablename__ = "alerts"

    id = db.Column(db.Integer, primary_key=True)
    alert_type = db.Column(db.String(50), nullable=False)  # performance, activity, threshold
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    severity = db.Column(db.String(20), default="info")  # info, warning, error, critical
    status = db.Column(db.String(20), default="active")  # active, acknowledged, resolved
    client_id = db.Column(db.Integer, db.ForeignKey("clients.id"), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    alert_data = db.Column(db.JSON)  # Additional alert data
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    acknowledged_at = db.Column(db.DateTime, nullable=True)
    acknowledged_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    resolved_at = db.Column(db.DateTime, nullable=True)
    resolved_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    # Relationships
    client = db.relationship("Client", backref="alerts")
    user = db.relationship("User", foreign_keys=[user_id], backref="alerts")
    acknowledged_user = db.relationship("User", foreign_keys=[acknowledged_by], backref="acknowledged_alerts")
    resolved_user = db.relationship("User", foreign_keys=[resolved_by], backref="resolved_alerts")


# Security Monitoring Models
class SecurityEvent(db.Model):
    """Track security-related events and incidents"""
    __tablename__ = "security_events"
    
    id = db.Column(db.Integer, primary_key=True)
    event_type = db.Column(db.String(50), nullable=False)  # login_failed, suspicious_transaction, ip_blocked, etc.
    severity = db.Column(db.String(20), default="medium")  # low, medium, high, critical
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    ip_address = db.Column(db.String(45), nullable=True)  # IPv4 or IPv6
    user_agent = db.Column(db.Text, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    client_id = db.Column(db.Integer, db.ForeignKey("clients.id"), nullable=True)
    transaction_id = db.Column(db.Integer, db.ForeignKey("transactions.id"), nullable=True)
    event_data = db.Column(db.JSON)  # Additional event-specific data
    status = db.Column(db.String(20), default="active")  # active, investigated, resolved, false_positive
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    resolved_at = db.Column(db.DateTime, nullable=True)
    resolved_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    
    # Relationships
    user = db.relationship("User", foreign_keys=[user_id], backref="security_events")
    client = db.relationship("Client", backref="security_events")
    transaction = db.relationship("Transaction", backref="security_events")
    resolver = db.relationship("User", foreign_keys=[resolved_by], backref="resolved_security_events")


class IPBlacklist(db.Model):
    """Track blocked IP addresses and their reasons"""
    __tablename__ = "ip_blacklist"
    
    id = db.Column(db.Integer, primary_key=True)
    ip_address = db.Column(db.String(45), nullable=False, unique=True)
    reason = db.Column(db.String(200), nullable=False)
    blocked_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    blocked_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=True)  # None for permanent blocks
    is_active = db.Column(db.Boolean, default=True)
    event_count = db.Column(db.Integer, default=1)  # Number of events that led to blocking
    
    # Relationships
    blocker = db.relationship("User", backref="blocked_ips")


class RateLimit(db.Model):
    """Track API rate limiting and abuse"""
    __tablename__ = "rate_limits"
    
    id = db.Column(db.Integer, primary_key=True)
    identifier = db.Column(db.String(100), nullable=False)  # IP, user_id, client_id, etc.
    identifier_type = db.Column(db.String(20), nullable=False)  # ip, user, client, api_key
    endpoint = db.Column(db.String(200), nullable=True)  # Specific API endpoint
    request_count = db.Column(db.Integer, default=1)
    window_start = db.Column(db.DateTime, default=datetime.utcnow)
    window_duration = db.Column(db.Integer, default=3600)  # Seconds
    limit_threshold = db.Column(db.Integer, default=100)  # Max requests per window
    is_blocked = db.Column(db.Boolean, default=False)
    blocked_until = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class FraudDetection(db.Model):
    """Track fraud detection patterns and rules"""
    __tablename__ = "fraud_detection"
    
    id = db.Column(db.Integer, primary_key=True)
    transaction_id = db.Column(db.Integer, db.ForeignKey("transactions.id"), nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey("clients.id"), nullable=False)
    risk_score = db.Column(db.Float, nullable=False)  # 0.0 to 1.0
    risk_factors = db.Column(db.JSON)  # List of risk factors detected
    fraud_rules_triggered = db.Column(db.JSON)  # Rules that were triggered
    status = db.Column(db.String(20), default="pending")  # pending, approved, rejected, manual_review
    reviewed_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    review_notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    transaction = db.relationship("Transaction", backref="fraud_analysis")
    client = db.relationship("Client", backref="fraud_analysis")
    reviewer = db.relationship("User", backref="fraud_reviews")


class AlertRule(db.Model):
    __tablename__ = "alert_rules"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    alert_type = db.Column(db.String(50), nullable=False)
    metric = db.Column(db.String(50), nullable=False)  # success_rate, transaction_count, revenue, inactivity
    threshold_value = db.Column(db.Float, nullable=False)
    threshold_operator = db.Column(db.String(10), nullable=False)  # >, <, >=, <=, ==, !=
    time_window = db.Column(db.Integer, default=24)  # hours
    is_active = db.Column(db.Boolean, default=True)
    client_id = db.Column(db.Integer, db.ForeignKey("clients.id"), nullable=True)  # null = global rule
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    client = db.relationship("Client", backref="alert_rules")
