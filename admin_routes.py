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
)
from models import (
    db,
    User,
    Client,
    Service,
    ServiceField,
    ClientService,
    Transaction,
    ApiLog,
)
from auth import admin_required, super_admin_required
from auth import generate_app_id, generate_api_credentials
from flask_jwt_extended import jwt_required, get_jwt_identity
import json
from datetime import datetime
from sqlalchemy import text

admin = Blueprint("admin", __name__)
logger = logging.getLogger(__name__)


# Helper: create default status function for a given client/service/route
def _create_status_function_for(
    client_app_id: str, service_name: str, route_name: str
) -> None:
    func_name = f"{client_app_id}_{service_name}_{route_name}Status"
    command = f"{route_name}Status"
    create_fn_sql = f"""
    CREATE OR REPLACE FUNCTION public."{func_name}"(unique_id text, data_input json)
    RETURNS TABLE(results json)
    LANGUAGE plpgsql
    AS $function$
    DECLARE
        _status VARCHAR(50):='200';
        _type VARCHAR(50):='object';
        _message TEXT:='Transaction status retrieved';
        _version VARCHAR(50):='1.0.0';
        _action VARCHAR(50):='OUTPUT';
        _command VARCHAR(50):='{command}';
        _servicename VARCHAR(50) :='{service_name}';
        _appId VARCHAR(50) :='{client_app_id}';
        _appName VARCHAR(50) :='Default Client';
        _entityName VARCHAR(50) :='Default Entity';
        _country VARCHAR(50) :='Default Country';
        _transaction_data json;
        _f000 text := COALESCE(data_input->>'f000', NULL);
        _f001 text := COALESCE(data_input->>'f001', NULL);
        _f002 text := COALESCE(data_input->>'f002', NULL);
        _f003 text := COALESCE(data_input->>'f003', NULL);
        _f010 text := COALESCE(data_input->>'f010', NULL);
    BEGIN
        RAISE NOTICE '[{command}] Input unique_id: %', unique_id;
        RAISE NOTICE '[{command}] Raw data_input: %', data_input;
        RAISE NOTICE '[{command}] f000(service)=% f001=% f002(route)=% f003(app_id)=% f010(unique_id)=%', _f000, _f001, _f002, _f003, _f010;

        RAISE NOTICE '[{command}] Querying transactions by unique_id=%', unique_id;

        SELECT json_build_object(
            'unique_id', t.unique_id,
            'status', t.status,
            'amount', t.amount,
            'mobile_number', t.mobile_number,
            'device_id', t.device_id,
            'created_at', t.created_at,
            'updated_at', t.updated_at,
            'request_payload', t.request_payload,
            'response_payload', t.response_payload
        )
        INTO _transaction_data
        FROM transactions t
        WHERE t.unique_id = $1;

        IF _transaction_data IS NULL THEN
            _status := '404';
            _message := 'Transaction not found';
            _action := 'ERROR';
            RAISE NOTICE '[{command}] Transaction not found for unique_id=%', unique_id;
        ELSE
            RAISE NOTICE '[{command}] Transaction found for unique_id=%', unique_id;
        END IF;

        results := json_build_object(
            'status', _status,
            'type', _type,
            'message', _message,
            'version', _version,
            'action', _action,
            'command', _command,
            'appName', _appName,
            'serviceurl', 'N/A',
            'servicepayload', json_build_array(
                json_build_object('i', 0, 'v', _appId),
                json_build_object('i', 1, 'v', _appName),
                json_build_object('i', 2, 'v', _entityName),
                json_build_object('i', 3, 'v', _servicename),
                json_build_object('i', 4, 'v', _country)
            ),
            'transaction_data', _transaction_data
        );
        RAISE NOTICE '[{command}] Returning results with status=% action=%', _status, _action;

        RETURN NEXT;
    END;
    $function$;
    """
    db.session.execute(text(create_fn_sql))
    db.session.commit()


# Admin Dashboard
@admin.route("/dashboard")
@admin_required
def dashboard():
    """Admin dashboard"""
    try:
        # Get statistics
        total_clients = Client.query.count()
        total_services = Service.query.count()
        total_transactions = Transaction.query.count()
        active_clients = Client.query.filter_by(is_active=True).count()

        # Recent transactions
        recent_transactions = (
            Transaction.query.order_by(Transaction.created_at.desc()).limit(10).all()
        )

        # Recent API logs
        recent_logs = ApiLog.query.order_by(ApiLog.created_at.desc()).limit(10).all()

        return render_template(
            "admin/dashboard.html",
            total_clients=total_clients,
            total_services=total_services,
            total_transactions=total_transactions,
            active_clients=active_clients,
            recent_transactions=recent_transactions,
            recent_logs=recent_logs,
        )
    except Exception as e:
        flash(f"Error loading dashboard: {str(e)}", "error")
        return redirect(url_for("admin.dashboard"))


# Client Management
@admin.route("/clients")
@admin_required
def clients():
    """List all clients"""
    try:
        page = request.args.get("page", 1, type=int)
        clients = Client.query.order_by(Client.created_at.desc()).paginate(
            page=page, per_page=20, error_out=False
        )
        return render_template("admin/clients.html", clients=clients)
    except Exception as e:
        flash(f"Error loading clients: {str(e)}", "error")
        return redirect(url_for("admin.dashboard"))


@admin.route("/clients/new", methods=["GET", "POST"])
@admin_required
def new_client():
    """Create new client"""
    if request.method == "POST":
        try:
            # Generate credentials
            app_id = generate_app_id()
            api_username, api_password = generate_api_credentials()

            # Create client
            client = Client(
                app_id=app_id,
                company_name=request.form["company_name"],
                contact_person=request.form["contact_person"],
                email=request.form["email"],
                phone=request.form["phone"],
                address=request.form["address"],
            )
            client.set_api_password(api_password)
            client.api_username = api_username

            db.session.add(client)
            db.session.commit()

            flash(
                f"Client created successfully! App ID: {app_id}, Username: {api_username}, Password: {api_password}",
                "success",
            )
            return redirect(url_for("admin.clients"))

        except Exception as e:
            db.session.rollback()
            flash(f"Error creating client: {str(e)}", "error")

    return render_template("admin/new_client.html")


@admin.route("/clients/<int:client_id>")
@admin_required
def view_client(client_id):
    """View client details"""
    try:
        client = Client.query.get_or_404(client_id)
        transactions = (
            Transaction.query.filter_by(client_id=client_id)
            .order_by(Transaction.created_at.desc())
            .limit(50)
            .all()
        )

        return render_template(
            "admin/view_client.html", client=client, transactions=transactions
        )
    except Exception as e:
        flash(f"Error loading client: {str(e)}", "error")
        return redirect(url_for("admin.clients"))


@admin.route("/clients/<int:client_id>/edit", methods=["GET", "POST"])
@admin_required
def edit_client(client_id):
    """Edit client"""
    client = Client.query.get_or_404(client_id)

    if request.method == "POST":
        try:
            client.company_name = request.form["company_name"]
            client.contact_person = request.form["contact_person"]
            client.email = request.form["email"]
            client.phone = request.form["phone"]
            client.address = request.form["address"]
            # New: callback_url (optional)
            client.callback_url = request.form.get("callback_url") or None
            client.is_active = "is_active" in request.form

            db.session.commit()
            flash("Client updated successfully!", "success")
            return redirect(url_for("admin.view_client", client_id=client_id))

        except Exception as e:
            db.session.rollback()
            flash(f"Error updating client: {str(e)}", "error")

    return render_template("admin/edit_client.html", client=client)


# Service Management
@admin.route("/services")
@admin_required
def services():
    """List all services"""
    try:
        services = Service.query.order_by(Service.name).all()
        return render_template("admin/services.html", services=services)
    except Exception as e:
        flash(f"Error loading services: {str(e)}", "error")
        return redirect(url_for("admin.dashboard"))


@admin.route("/services/new", methods=["GET", "POST"])
@admin_required
def new_service():
    """Create new service"""
    if request.method == "POST":
        try:
            service = Service(
                name=request.form["name"],
                display_name=request.form["display_name"],
                description=request.form["description"],
                service_url=request.form["service_url"],
            )

            db.session.add(service)
            db.session.commit()

            # Add default service fields
            default_fields = [
                ("f000", "Service Name", "string", True, "Name of the service"),
                ("f001", "SERVICE", "string", True, "Static Key"),
                ("f002", "Service Route", "string", True, "Route for the service"),
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
            flash("Service created successfully!", "success")
            return redirect(url_for("admin.services"))

        except Exception as e:
            db.session.rollback()
            flash(f"Error creating service: {str(e)}", "error")

    return render_template("admin/new_service.html")


@admin.route("/services/<int:service_id>")
@admin_required
def view_service(service_id):
    """View service details"""
    try:
        service = Service.query.get_or_404(service_id)
        service_fields = (
            ServiceField.query.filter_by(service_id=service_id)
            .order_by(ServiceField.field_code)
            .all()
        )

        return render_template(
            "admin/view_service.html", service=service, service_fields=service_fields
        )
    except Exception as e:
        flash(f"Error loading service: {str(e)}", "error")
        return redirect(url_for("admin.services"))


# Client Service Assignment
@admin.route("/clients/<int:client_id>/services")
@admin_required
def client_services(client_id):
    """Manage client services"""
    try:
        client = Client.query.get_or_404(client_id)
        all_services = Service.query.filter_by(is_active=True).all()
        client_services = ClientService.query.filter_by(
            client_id=client_id, is_active=True
        ).all()

        # Get service IDs that client already has access to (only active ones)
        assigned_service_ids = [cs.service_id for cs in client_services]

        return render_template(
            "admin/client_services.html",
            client=client,
            all_services=all_services,
            assigned_service_ids=assigned_service_ids,
        )
    except Exception as e:
        flash(f"Error loading client services: {str(e)}", "error")
        return redirect(url_for("admin.clients"))


@admin.route(
    "/clients/<int:client_id>/services/<int:service_id>/assign", methods=["POST"]
)
@admin_required
def assign_service(client_id, service_id):
    """Assign service to client"""
    try:
        # Check if already assigned
        existing = ClientService.query.filter_by(
            client_id=client_id, service_id=service_id
        ).first()

        if existing:
            existing.is_active = True
        else:
            client_service = ClientService(client_id=client_id, service_id=service_id)
            db.session.add(client_service)

        db.session.commit()

        # Auto-create a default status function for common route 'collection'
        try:
            client = Client.query.get(client_id)
            service = Service.query.get(service_id)
            if client and service and client.app_id and service.name:
                # Default route seed; more routes can be added later from UI/script
                _create_status_function_for(client.app_id, service.name, "collection")
        except Exception as gen_err:
            # Do not block assignment if function creation fails
            current_app.logger.warning(
                f"Status function generation skipped: {str(gen_err)}"
            )

        flash("Service assigned successfully!", "success")

    except Exception as e:
        db.session.rollback()
        flash(f"Error assigning service: {str(e)}", "error")

    return redirect(url_for("admin.client_services", client_id=client_id))


@admin.route(
    "/clients/<int:client_id>/services/<int:service_id>/revoke", methods=["POST"]
)
@admin_required
def revoke_service(client_id, service_id):
    """Revoke service from client"""
    try:
        client_service = ClientService.query.filter_by(
            client_id=client_id, service_id=service_id
        ).first()

        if client_service:
            client_service.is_active = False
            db.session.commit()
            flash("Service revoked successfully!", "success")

    except Exception as e:
        db.session.rollback()
        flash(f"Error revoking service: {str(e)}", "error")

    return redirect(url_for("admin.client_services", client_id=client_id))


# Transaction Management
@admin.route("/transactions")
@admin_required
def transactions():
    """List all transactions"""
    try:
        page = request.args.get("page", 1, type=int)
        transactions = Transaction.query.order_by(
            Transaction.created_at.desc()
        ).paginate(page=page, per_page=50, error_out=False)

        return render_template("admin/transactions.html", transactions=transactions)
    except Exception as e:
        flash(f"Error loading transactions: {str(e)}", "error")
        return redirect(url_for("admin.dashboard"))


@admin.route("/transactions/<string:unique_id>")
@admin_required
def view_transaction(unique_id):
    """View transaction details"""
    try:
        print(f"DEBUG: Looking for transaction with unique_id: {unique_id}")

        # Check if transaction exists
        transaction = Transaction.query.filter_by(unique_id=unique_id).first()
        if not transaction:
            print(f"DEBUG: Transaction {unique_id} not found in database")
            flash(f"Transaction {unique_id} not found", "error")
            return redirect(url_for("admin.transactions"))

        print(
            f"DEBUG: Found transaction: {transaction.unique_id}, status: {transaction.status}"
        )
        print(f"DEBUG: About to render template with transaction data")

        # Test template rendering
        try:
            result = render_template(
                "admin/view_transaction.html", transaction=transaction
            )
            print(f"DEBUG: Template rendered successfully, length: {len(result)}")
            return result
        except Exception as template_error:
            print(f"DEBUG: Template rendering error: {str(template_error)}")
            flash(f"Template error: {str(template_error)}", "error")
            return redirect(url_for("admin.transactions"))

    except Exception as e:
        print(f"DEBUG: Error loading transaction {unique_id}: {str(e)}")
        flash(f"Error loading transaction: {str(e)}", "error")
        return redirect(url_for("admin.transactions"))


# API Logs
@admin.route("/api-logs")
@admin_required
def api_logs():
    """List API logs"""
    try:
        page = request.args.get("page", 1, type=int)
        logs = ApiLog.query.order_by(ApiLog.created_at.desc()).paginate(
            page=page, per_page=50, error_out=False
        )

        return render_template("admin/api_logs.html", logs=logs)
    except Exception as e:
        flash(f"Error loading API logs: {str(e)}", "error")
        return redirect(url_for("admin.dashboard"))


# User Management (Super Admin only)
@admin.route("/users")
@super_admin_required
def users():
    """List all users (super admin only)"""
    try:
        users = User.query.order_by(User.created_at.desc()).all()
        return render_template("admin/users.html", users=users)
    except Exception as e:
        flash(f"Error loading users: {str(e)}", "error")
        return redirect(url_for("admin.dashboard"))


@admin.route("/users/new", methods=["GET", "POST"])
@super_admin_required
def new_user():
    """Create new user (super admin only)"""
    if request.method == "POST":
        try:
            user = User(
                username=request.form["username"],
                email=request.form["email"],
                role=request.form["role"],
            )
            user.set_password(request.form["password"])

            db.session.add(user)
            db.session.commit()

            flash("User created successfully!", "success")
            return redirect(url_for("admin.users"))

        except Exception as e:
            db.session.rollback()
            flash(f"Error creating user: {str(e)}", "error")

    return render_template("admin/new_user.html")


@admin.route("/users/<int:user_id>")
@super_admin_required
def view_user(user_id):
    """View user details (super admin only)"""
    try:
        user = User.query.get_or_404(user_id)
        return render_template("admin/view_user.html", user=user)
    except Exception as e:
        flash(f"Error loading user: {str(e)}", "error")
        return redirect(url_for("admin.users"))


@admin.route("/users/<int:user_id>/edit", methods=["GET", "POST"])
@super_admin_required
def edit_user(user_id):
    """Edit user details (super admin only)"""
    try:
        user = User.query.get_or_404(user_id)

        if request.method == "POST":
            user.username = request.form["username"]
            user.email = request.form["email"]
            user.role = request.form["role"]

            if request.form.get("password"):
                user.set_password(request.form["password"])

            db.session.commit()
            flash("User updated successfully!", "success")
            return redirect(url_for("admin.view_user", user_id=user_id))

        return render_template("admin/edit_user.html", user=user)
    except Exception as e:
        db.session.rollback()
        flash(f"Error updating user: {str(e)}", "error")
        return redirect(url_for("admin.users"))


@admin.route("/users/<int:user_id>/toggle-status", methods=["POST"])
@super_admin_required
def toggle_user_status(user_id):
    """Toggle user active status (super admin only)"""
    try:
        user = User.query.get_or_404(user_id)

        # Prevent deactivating yourself
        if user.id == current_app.config.get(
            "USER_ID"
        ):  # Assuming USER_ID is set in config or context
            return jsonify(
                {"success": False, "message": "Cannot deactivate your own account"}
            )

        user.is_active = not user.is_active
        db.session.commit()

        status = "activated" if user.is_active else "deactivated"
        return jsonify({"success": True, "message": f"User {status} successfully"})
    except Exception as e:
        db.session.rollback()
        return jsonify(
            {"success": False, "message": f"Error updating user status: {str(e)}"}
        )


# Client Status Management
@admin.route("/clients/<int:client_id>/toggle-status", methods=["POST"])
@admin_required
def toggle_client_status(client_id):
    """Toggle client active/inactive status"""
    try:
        client = Client.query.get_or_404(client_id)

        # Debug: Log the current status
        print(f"DEBUG: Client {client_id} current status: {client.is_active}")

        # Toggle the status
        old_status = client.is_active
        client.is_active = not client.is_active

        # Debug: Log the new status
        print(f"DEBUG: Client {client_id} new status: {client.is_active}")

        # Commit the change
        db.session.commit()

        # Verify the change was committed
        db.session.refresh(client)
        print(f"DEBUG: Client {client_id} status after commit: {client.is_active}")

        status = "activated" if client.is_active else "deactivated"
        flash(
            f"Client {status} successfully! Status changed from {'Active' if old_status else 'Inactive'} to {'Active' if client.is_active else 'Inactive'}",
            "success",
        )

    except Exception as e:
        db.session.rollback()
        print(f"DEBUG: Error toggling client status: {str(e)}")
        flash(f"Error toggling client status: {str(e)}", "error")

    return redirect(url_for("admin.view_client", client_id=client_id))


# Client Credential Regeneration
@admin.route("/clients/<int:client_id>/regenerate-credentials", methods=["POST"])
@admin_required
def regenerate_credentials(client_id):
    """Regenerate client API credentials (username and password only)"""
    try:
        print(f"DEBUG: Starting credential regeneration for client {client_id}")
        client = Client.query.get_or_404(client_id)

        # Store the current app_id for display
        current_app_id = client.app_id
        print(f"DEBUG: Current App ID: {current_app_id}")

        # Generate new API credentials only (keep app_id unchanged)
        new_api_username, new_api_password = generate_api_credentials()
        print(f"DEBUG: Generated new credentials - Username: {new_api_username}")

        # Update only the API credentials, keep app_id unchanged
        client.api_username = new_api_username
        client.set_api_password(new_api_password)

        db.session.commit()
        print(f"DEBUG: Credentials updated and committed to database")

        flash(
            f"API credentials regenerated successfully! App ID remains: {current_app_id}, New Username: {new_api_username}, New Password: {new_api_password}",
            "success",
        )
        print(f"DEBUG: Flash message set, about to redirect")

    except Exception as e:
        print(f"DEBUG: Error in credential regeneration: {str(e)}")
        db.session.rollback()
        flash(f"Error regenerating credentials: {str(e)}", "error")

    print(f"DEBUG: Returning redirect to client view")
    return redirect(url_for("admin.view_client", client_id=client_id))
