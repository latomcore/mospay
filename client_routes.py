import logging
from flask import (
    Blueprint,
    request,
    jsonify,
    render_template,
    redirect,
    url_for,
    flash,
    current_app,
    session,
)
from flask_login import login_user, logout_user, login_required, current_user
from models import db, Client, Transaction, ApiLog
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from datetime import datetime, timedelta
from sqlalchemy import func, and_, or_
import json

client = Blueprint("client", __name__)
logger = logging.getLogger(__name__)


def client_required(f):
    """Decorator to require client authentication"""
    def decorated_function(*args, **kwargs):
        if not session.get('client_id'):
            flash('Please log in to access the client portal.', 'error')
            return redirect(url_for('client.login'))
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function


@client.route("/login", methods=["GET", "POST"])
def login():
    """Client login page"""
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()
        
        if not email or not password:
            flash("Please provide both email and password.", "error")
            return render_template("client/login.html")
        
        # Find client by email
        client_obj = Client.query.filter_by(email=email, is_active=True).first()
        
        if not client_obj:
            flash("Invalid email or password.", "error")
            return render_template("client/login.html")
        
        # Check if account is locked
        if client_obj.is_account_locked():
            flash("Account is temporarily locked due to multiple failed login attempts. Please try again later.", "error")
            return render_template("client/login.html")
        
        # Check if client has portal password set
        if not client_obj.portal_password_hash:
            flash("Portal access not configured. Please contact your administrator.", "error")
            return render_template("client/login.html")
        
        # Verify password
        if client_obj.check_portal_password(password):
            # Successful login
            client_obj.update_last_login()
            session['client_id'] = client_obj.id
            session['client_app_id'] = client_obj.app_id
            session['client_company'] = client_obj.company_name
            session['client_email'] = client_obj.email
            
            flash(f"Welcome back, {client_obj.company_name}!", "success")
            return redirect(url_for("client.dashboard"))
        else:
            # Failed login
            client_obj.increment_login_attempts()
            flash("Invalid email or password.", "error")
            return render_template("client/login.html")
    
    return render_template("client/login.html")


@client.route("/logout")
@client_required
def logout():
    """Client logout"""
    session.pop('client_id', None)
    session.pop('client_app_id', None)
    session.pop('client_company', None)
    session.pop('client_email', None)
    flash("You have been logged out successfully.", "info")
    return redirect(url_for("client.login"))


@client.route("/dashboard")
@client_required
def dashboard():
    """Client dashboard with overview metrics"""
    try:
        client_id = session.get('client_id')
        client_obj = Client.query.get(client_id)
        
        if not client_obj:
            flash("Client not found.", "error")
            return redirect(url_for("client.login"))
        
        # Calculate metrics
        today = datetime.now().date()
        last_30_days = today - timedelta(days=30)
        last_7_days = today - timedelta(days=7)
        
        # Total transactions
        total_transactions = Transaction.query.filter_by(client_id=client_id).count()
        
        # Today's transactions
        today_transactions = Transaction.query.filter(
            Transaction.client_id == client_id,
            func.date(Transaction.created_at) == today
        ).count()
        
        # Last 30 days transactions
        last_30d_transactions = Transaction.query.filter(
            Transaction.client_id == client_id,
            func.date(Transaction.created_at) >= last_30_days
        ).count()
        
        # Success rate (last 30 days)
        successful_transactions = Transaction.query.filter(
            Transaction.client_id == client_id,
            func.date(Transaction.created_at) >= last_30_days,
            Transaction.status == "completed"
        ).count()
        
        success_rate = (
            (successful_transactions / last_30d_transactions * 100)
            if last_30d_transactions > 0
            else 0
        )
        
        # Total revenue (last 30 days)
        total_revenue = db.session.query(func.sum(Transaction.amount)).filter(
            Transaction.client_id == client_id,
            func.date(Transaction.created_at) >= last_30_days,
            Transaction.status == "completed"
        ).scalar() or 0
        
        # Active services count
        active_services = len(client_obj.services)
        
        # Recent transactions (last 10)
        recent_transactions = Transaction.query.filter_by(
            client_id=client_id
        ).order_by(Transaction.created_at.desc()).limit(10).all()
        
        # Recent API calls (last 10)
        recent_api_calls = ApiLog.query.filter_by(
            client_id=client_id
        ).order_by(ApiLog.created_at.desc()).limit(10).all()
        
        # Chart data for last 30 days
        chart_data = []
        for i in range(30):
            date = today - timedelta(days=i)
            day_transactions = Transaction.query.filter(
                Transaction.client_id == client_id,
                func.date(Transaction.created_at) == date
            ).count()
            
            day_revenue = db.session.query(func.sum(Transaction.amount)).filter(
                Transaction.client_id == client_id,
                func.date(Transaction.created_at) == date,
                Transaction.status == "completed"
            ).scalar() or 0
            
            chart_data.append({
                'date': date.strftime('%Y-%m-%d'),
                'transactions': day_transactions,
                'revenue': float(day_revenue)
            })
        
        chart_data.reverse()  # Show oldest to newest
        
        return render_template("client/dashboard.html",
                             client=client_obj,
                             total_transactions=total_transactions,
                             today_transactions=today_transactions,
                             last_30d_transactions=last_30d_transactions,
                             success_rate=round(success_rate, 2),
                             total_revenue=total_revenue,
                             active_services=active_services,
                             recent_transactions=recent_transactions,
                             recent_api_calls=recent_api_calls,
                             chart_data=chart_data)
        
    except Exception as e:
        logger.error(f"Error loading client dashboard: {str(e)}")
        flash(f"Error loading dashboard: {str(e)}", "error")
        return redirect(url_for("client.login"))


@client.route("/transactions")
@client_required
def transactions():
    """Client transaction management"""
    try:
        client_id = session.get('client_id')
        page = request.args.get("page", 1, type=int)
        per_page = 20
        
        # Get filter parameters
        status_filter = request.args.get("status", "")
        service_filter = request.args.get("service", "")
        date_from = request.args.get("date_from", "")
        date_to = request.args.get("date_to", "")
        search = request.args.get("search", "")
        
        # Build query
        query = Transaction.query.filter_by(client_id=client_id)
        
        # Apply filters
        if status_filter:
            query = query.filter(Transaction.status == status_filter)
        
        if service_filter:
            query = query.filter(Transaction.service_name == service_filter)
        
        if date_from:
            try:
                date_from_obj = datetime.strptime(date_from, "%Y-%m-%d").date()
                query = query.filter(func.date(Transaction.created_at) >= date_from_obj)
            except ValueError:
                pass
        
        if date_to:
            try:
                date_to_obj = datetime.strptime(date_to, "%Y-%m-%d").date()
                query = query.filter(func.date(Transaction.created_at) <= date_to_obj)
            except ValueError:
                pass
        
        if search:
            query = query.filter(
                or_(
                    Transaction.unique_id.ilike(f"%{search}%"),
                    Transaction.reference.ilike(f"%{search}%"),
                    Transaction.customer_name.ilike(f"%{search}%")
                )
            )
        
        # Order by creation date (newest first)
        query = query.order_by(Transaction.created_at.desc())
        
        # Paginate
        transactions = query.paginate(
            page=page, per_page=per_page, error_out=False
        )
        
        # Get unique services for filter dropdown
        services = db.session.query(Transaction.service_name).filter_by(
            client_id=client_id
        ).distinct().all()
        service_options = [s[0] for s in services if s[0]]
        
        return render_template("client/transactions.html",
                             transactions=transactions,
                             service_options=service_options,
                             current_filters={
                                 'status': status_filter,
                                 'service': service_filter,
                                 'date_from': date_from,
                                 'date_to': date_to,
                                 'search': search
                             })
        
    except Exception as e:
        logger.error(f"Error loading client transactions: {str(e)}")
        flash(f"Error loading transactions: {str(e)}", "error")
        return redirect(url_for("client.dashboard"))


@client.route("/transactions/<string:unique_id>")
@client_required
def transaction_detail(unique_id):
    """Client transaction detail view"""
    try:
        client_id = session.get('client_id')
        transaction = Transaction.query.filter_by(
            client_id=client_id,
            unique_id=unique_id
        ).first()
        
        if not transaction:
            flash("Transaction not found.", "error")
            return redirect(url_for("client.transactions"))
        
        # Get related API logs
        api_logs = ApiLog.query.filter_by(
            client_id=client_id,
            transaction_id=transaction.id
        ).order_by(ApiLog.created_at.desc()).all()
        
        return render_template("client/transaction_detail.html",
                             transaction=transaction,
                             api_logs=api_logs)
        
    except Exception as e:
        logger.error(f"Error loading transaction detail: {str(e)}")
        flash(f"Error loading transaction details: {str(e)}", "error")
        return redirect(url_for("client.transactions"))


@client.route("/services")
@client_required
def services():
    """Client service management"""
    try:
        client_id = session.get('client_id')
        client_obj = Client.query.get(client_id)
        
        if not client_obj:
            flash("Client not found.", "error")
            return redirect(url_for("client.login"))
        
        # Get client services with performance metrics
        services_data = []
        for client_service in client_obj.services:
            service = client_service.service
            
            # Get service performance metrics (last 30 days)
            last_30_days = datetime.now().date() - timedelta(days=30)
            
            total_transactions = Transaction.query.filter(
                Transaction.client_id == client_id,
                Transaction.service_name == service.name
            ).count()
            
            last_30d_transactions = Transaction.query.filter(
                Transaction.client_id == client_id,
                Transaction.service_name == service.name,
                func.date(Transaction.created_at) >= last_30_days
            ).count()
            
            successful_transactions = Transaction.query.filter(
                Transaction.client_id == client_id,
                Transaction.service_name == service.name,
                func.date(Transaction.created_at) >= last_30_days,
                Transaction.status == "completed"
            ).count()
            
            success_rate = (
                (successful_transactions / last_30d_transactions * 100)
                if last_30d_transactions > 0
                else 0
            )
            
            services_data.append({
                'service': service,
                'client_service': client_service,
                'total_transactions': total_transactions,
                'last_30d_transactions': last_30d_transactions,
                'success_rate': round(success_rate, 2)
            })
        
        return render_template("client/services.html",
                             client=client_obj,
                             services_data=services_data)
        
    except Exception as e:
        logger.error(f"Error loading client services: {str(e)}")
        flash(f"Error loading services: {str(e)}", "error")
        return redirect(url_for("client.dashboard"))


@client.route("/api-keys")
@client_required
def api_keys():
    """Client API key management"""
    try:
        client_id = session.get('client_id')
        client_obj = Client.query.get(client_id)
        
        if not client_obj:
            flash("Client not found.", "error")
            return redirect(url_for("client.login"))
        
        # Get API usage statistics (last 30 days)
        last_30_days = datetime.now().date() - timedelta(days=30)
        
        total_api_calls = ApiLog.query.filter_by(client_id=client_id).count()
        last_30d_api_calls = ApiLog.query.filter(
            ApiLog.client_id == client_id,
            func.date(ApiLog.created_at) >= last_30_days
        ).count()
        
        successful_api_calls = ApiLog.query.filter(
            ApiLog.client_id == client_id,
            func.date(ApiLog.created_at) >= last_30_days,
            ApiLog.status_code.between(200, 299)
        ).count()
        
        api_success_rate = (
            (successful_api_calls / last_30d_api_calls * 100)
            if last_30d_api_calls > 0
            else 0
        )
        
        return render_template("client/api_keys.html",
                             client=client_obj,
                             total_api_calls=total_api_calls,
                             last_30d_api_calls=last_30d_api_calls,
                             api_success_rate=round(api_success_rate, 2))
        
    except Exception as e:
        logger.error(f"Error loading client API keys: {str(e)}")
        flash(f"Error loading API keys: {str(e)}", "error")
        return redirect(url_for("client.dashboard"))


@client.route("/settings")
@client_required
def settings():
    """Client settings and profile management"""
    try:
        client_id = session.get('client_id')
        client_obj = Client.query.get(client_id)
        
        if not client_obj:
            flash("Client not found.", "error")
            return redirect(url_for("client.login"))
        
        return render_template("client/settings.html", client=client_obj)
        
    except Exception as e:
        logger.error(f"Error loading client settings: {str(e)}")
        flash(f"Error loading settings: {str(e)}", "error")
        return redirect(url_for("client.dashboard"))


@client.route("/settings/change-password", methods=["POST"])
@client_required
def change_password():
    """Change client portal password"""
    try:
        client_id = session.get('client_id')
        client_obj = Client.query.get(client_id)
        
        if not client_obj:
            flash("Client not found.", "error")
            return redirect(url_for("client.login"))
        
        current_password = request.form.get("current_password", "").strip()
        new_password = request.form.get("new_password", "").strip()
        confirm_password = request.form.get("confirm_password", "").strip()
        
        # Validate input
        if not current_password or not new_password or not confirm_password:
            flash("All fields are required.", "error")
            return redirect(url_for("client.settings"))
        
        if new_password != confirm_password:
            flash("New passwords do not match.", "error")
            return redirect(url_for("client.settings"))
        
        if len(new_password) < 6:
            flash("Password must be at least 6 characters long.", "error")
            return redirect(url_for("client.settings"))
        
        # Verify current password
        if not client_obj.check_portal_password(current_password):
            flash("Current password is incorrect.", "error")
            return redirect(url_for("client.settings"))
        
        # Update password
        client_obj.set_portal_password(new_password)
        db.session.commit()
        
        flash("Password updated successfully.", "success")
        return redirect(url_for("client.settings"))
        
    except Exception as e:
        logger.error(f"Error changing client password: {str(e)}")
        flash(f"Error updating password: {str(e)}", "error")
        return redirect(url_for("client.settings"))
