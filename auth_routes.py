from flask import (
    Blueprint,
    request,
    jsonify,
    render_template,
    redirect,
    url_for,
    flash,
    session,
)
from models import db, User
from auth import admin_required
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from flask_bcrypt import check_password_hash
from flask_login import login_user, logout_user, login_required, current_user
import datetime

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """User login"""
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password) and user.is_active:
            # Create JWT token
            token = create_access_token(identity=user.id)

            # Login user with Flask-Login
            login_user(user, remember=True)

            # Store in session for admin panel (for backward compatibility)
            session["user_id"] = user.id
            session["username"] = user.username
            session["role"] = user.role
            session["jwt_token"] = token

            flash("Login successful!", "success")
            return redirect(url_for("admin.dashboard"))
        else:
            flash("Invalid username or password", "error")

    return render_template("auth/login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    """User logout"""
    logout_user()
    session.clear()
    flash("You have been logged out", "info")
    return redirect(url_for("auth.login"))


@auth_bp.route("/change-password", methods=["GET", "POST"])
@jwt_required()
def change_password():
    """Change user password"""
    current_user_id = get_jwt_identity()
    user = User.query.get(current_user_id)

    if request.method == "POST":
        current_password = request.form["current_password"]
        new_password = request.form["new_password"]
        confirm_password = request.form["confirm_password"]

        if not user.check_password(current_password):
            flash("Current password is incorrect", "error")
        elif new_password != confirm_password:
            flash("New passwords do not match", "error")
        elif len(new_password) < 6:
            flash("Password must be at least 6 characters long", "error")
        else:
            user.set_password(new_password)
            db.session.commit()
            flash("Password changed successfully!", "success")
            return redirect(url_for("admin.dashboard"))

    return render_template("auth/change_password.html")


@auth_bp.route("/profile")
def profile():
    """User profile"""
    # Check if user is authenticated via session (web) or JWT (API)
    if session.get("user_id"):
        # Session-based authentication (web users)
        current_user_id = session.get("user_id")
        user = User.query.get(current_user_id)
    else:
        # JWT-based authentication (API users)
        try:
            from flask_jwt_extended import jwt_required, get_jwt_identity

            current_user_id = get_jwt_identity()
            user = User.query.get(current_user_id)
        except:
            flash("Please log in to view your profile", "error")
            return redirect(url_for("auth.login"))

    if not user:
        flash("User not found", "error")
        return redirect(url_for("auth.login"))

    return render_template("auth/profile.html", user=user)


@auth_bp.route("/profile/edit", methods=["GET", "POST"])
def edit_profile():
    """Edit user profile"""
    # Check if user is authenticated via session (web) or JWT (API)
    if session.get("user_id"):
        # Session-based authentication (web users)
        current_user_id = session.get("user_id")
        user = User.query.get(current_user_id)
    else:
        # JWT-based authentication (API users)
        try:
            from flask_jwt_extended import jwt_required, get_jwt_identity

            current_user_id = get_jwt_identity()
            user = User.query.get(current_user_id)
        except:
            flash("Please log in to edit your profile", "error")
            return redirect(url_for("auth.login"))

    if not user:
        flash("User not found", "error")
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        user.email = request.form["email"]

        db.session.commit()
        flash("Profile updated successfully!", "success")
        return redirect(url_for("auth.profile"))

    return render_template("auth/edit_profile.html", user=user)


# API endpoint for JWT token validation
@auth_bp.route("/api/validate-token", methods=["POST"])
@jwt_required()
def validate_token():
    """Validate JWT token"""
    current_user_id = get_jwt_identity()
    user = User.query.get(current_user_id)

    if user and user.is_active:
        return jsonify(
            {
                "valid": True,
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "role": user.role,
                },
            }
        )
    else:
        return jsonify({"valid": False}), 401
