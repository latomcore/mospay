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
from flask_login import current_user
from models import (
    db,
    User,
    Client,
    Service,
    ServiceField,
    ClientService,
    Transaction,
    ApiLog,
    Alert,
    AlertRule,
    SecurityEvent,
    IPBlacklist,
    RateLimit,
    FraudDetection,
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
    """Enhanced admin dashboard with real-time metrics"""
    try:
        from datetime import datetime, timedelta

        # Basic statistics
        total_clients = Client.query.count()
        total_services = Service.query.count()
        total_transactions = Transaction.query.count()
        active_clients = Client.query.filter_by(is_active=True).count()

        # Enhanced statistics
        today = datetime.now().date()
        yesterday = today - timedelta(days=1)
        this_month = today.replace(day=1)
        last_month = (this_month - timedelta(days=1)).replace(day=1)

        # Today's metrics
        today_transactions = Transaction.query.filter(
            db.func.date(Transaction.created_at) == today
        ).count()

        # This month's metrics
        month_transactions = Transaction.query.filter(
            db.func.date(Transaction.created_at) >= this_month
        ).count()

        # Success rate (last 24 hours)
        last_24h = datetime.now() - timedelta(hours=24)
        recent_transactions_count = Transaction.query.filter(
            Transaction.created_at >= last_24h
        ).count()

        successful_transactions = Transaction.query.filter(
            Transaction.created_at >= last_24h, Transaction.status == "completed"
        ).count()

        success_rate = (
            (successful_transactions / recent_transactions_count * 100)
            if recent_transactions_count > 0
            else 0
        )

        # Revenue calculations (assuming amount field exists)
        today_revenue = (
            db.session.query(db.func.sum(Transaction.amount))
            .filter(
                db.func.date(Transaction.created_at) == today,
                Transaction.status == "completed",
            )
            .scalar()
            or 0
        )

        month_revenue = (
            db.session.query(db.func.sum(Transaction.amount))
            .filter(
                db.func.date(Transaction.created_at) >= this_month,
                Transaction.status == "completed",
            )
            .scalar()
            or 0
        )

        # Transaction volume by service (for charts)
        service_stats = (
            db.session.query(
                Service.name,
                Service.display_name,
                db.func.count(Transaction.id).label("count"),
            )
            .join(Transaction, Service.id == Transaction.service_id)
            .filter(Transaction.created_at >= last_24h)
            .group_by(Service.id, Service.name, Service.display_name)
            .all()
        )

        # Recent transactions
        recent_transactions = (
            Transaction.query.order_by(Transaction.created_at.desc()).limit(10).all()
        )

        # Recent API logs
        recent_logs = ApiLog.query.order_by(ApiLog.created_at.desc()).limit(10).all()

        # Alert statistics
        active_alerts = Alert.query.filter_by(status="active").count()
        critical_alerts = Alert.query.filter_by(
            status="active", severity="critical"
        ).count()
        warning_alerts = Alert.query.filter_by(
            status="active", severity="warning"
        ).count()
        total_alert_rules = AlertRule.query.filter_by(is_active=True).count()

        # Transaction trends (last 7 days for charts)
        last_7_days = []
        for i in range(7):
            date = today - timedelta(days=i)
            count = Transaction.query.filter(
                db.func.date(Transaction.created_at) == date
            ).count()
            last_7_days.append({"date": date.strftime("%Y-%m-%d"), "count": count})
        last_7_days.reverse()  # Show oldest to newest

        return render_template(
            "admin/dashboard.html",
            # Basic stats
            total_clients=total_clients,
            total_services=total_services,
            total_transactions=total_transactions,
            active_clients=active_clients,
            # Enhanced stats
            today_transactions=today_transactions,
            month_transactions=month_transactions,
            success_rate=round(success_rate, 1),
            today_revenue=today_revenue,
            month_revenue=month_revenue,
            # Alert stats
            active_alerts=active_alerts,
            critical_alerts=critical_alerts,
            warning_alerts=warning_alerts,
            total_alert_rules=total_alert_rules,
            # Chart data
            service_stats=service_stats,
            transaction_trends=last_7_days,
            # Recent data
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
    """List all clients with performance metrics"""
    try:
        from datetime import datetime, timedelta

        page = request.args.get("page", 1, type=int)
        clients_query = Client.query.order_by(Client.created_at.desc())

        # Get basic client data with pagination
        clients = clients_query.paginate(page=page, per_page=20, error_out=False)

        # Calculate performance metrics for each client
        today = datetime.now().date()
        last_30_days = today - timedelta(days=30)
        last_7_days = today - timedelta(days=7)

        client_performance = []
        for client in clients.items:
            # Get transaction counts
            total_transactions = Transaction.query.filter_by(
                client_id=client.id
            ).count()
            last_30d_transactions = Transaction.query.filter(
                Transaction.client_id == client.id,
                db.func.date(Transaction.created_at) >= last_30_days,
            ).count()
            last_7d_transactions = Transaction.query.filter(
                Transaction.client_id == client.id,
                db.func.date(Transaction.created_at) >= last_7_days,
            ).count()

            # Get success rate (last 30 days)
            successful_transactions = Transaction.query.filter(
                Transaction.client_id == client.id,
                db.func.date(Transaction.created_at) >= last_30_days,
                Transaction.status == "completed",
            ).count()

            success_rate = (
                (successful_transactions / last_30d_transactions * 100)
                if last_30d_transactions > 0
                else 0
            )

            # Get revenue (last 30 days)
            revenue_30d = (
                db.session.query(db.func.sum(Transaction.amount))
                .filter(
                    Transaction.client_id == client.id,
                    db.func.date(Transaction.created_at) >= last_30_days,
                    Transaction.status == "completed",
                )
                .scalar()
                or 0
            )

            # Get last transaction date
            last_transaction = (
                Transaction.query.filter_by(client_id=client.id)
                .order_by(Transaction.created_at.desc())
                .first()
            )

            client_performance.append(
                {
                    "client": client,
                    "total_transactions": total_transactions,
                    "last_30d_transactions": last_30d_transactions,
                    "last_7d_transactions": last_7d_transactions,
                    "success_rate": round(success_rate, 1),
                    "revenue_30d": revenue_30d,
                    "last_transaction": (
                        last_transaction.created_at if last_transaction else None
                    ),
                    "is_active_recently": (
                        last_transaction.created_at
                        >= (datetime.now() - timedelta(days=7))
                        if last_transaction
                        else False
                    ),
                }
            )

        return render_template(
            "admin/clients.html", clients=clients, client_performance=client_performance
        )
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
    """View client details with performance dashboard"""
    try:
        from datetime import datetime, timedelta

        client = Client.query.get_or_404(client_id)
        services = Service.query.all()
        client_services = ClientService.query.filter_by(client_id=client_id).all()

        # Performance metrics
        today = datetime.now().date()
        last_30_days = today - timedelta(days=30)
        last_7_days = today - timedelta(days=7)
        last_90_days = today - timedelta(days=90)

        # Transaction statistics
        total_transactions = Transaction.query.filter_by(client_id=client_id).count()
        last_30d_transactions = Transaction.query.filter(
            Transaction.client_id == client_id,
            db.func.date(Transaction.created_at) >= last_30_days,
        ).count()
        last_7d_transactions = Transaction.query.filter(
            Transaction.client_id == client_id,
            db.func.date(Transaction.created_at) >= last_7_days,
        ).count()

        # Success rates
        successful_30d = Transaction.query.filter(
            Transaction.client_id == client_id,
            db.func.date(Transaction.created_at) >= last_30_days,
            Transaction.status == "completed",
        ).count()

        success_rate_30d = (
            (successful_30d / last_30d_transactions * 100)
            if last_30d_transactions > 0
            else 0
        )

        # Revenue metrics
        revenue_30d = (
            db.session.query(db.func.sum(Transaction.amount))
            .filter(
                Transaction.client_id == client_id,
                db.func.date(Transaction.created_at) >= last_30_days,
                Transaction.status == "completed",
            )
            .scalar()
            or 0
        )

        revenue_7d = (
            db.session.query(db.func.sum(Transaction.amount))
            .filter(
                Transaction.client_id == client_id,
                db.func.date(Transaction.created_at) >= last_7_days,
                Transaction.status == "completed",
            )
            .scalar()
            or 0
        )

        # Transaction trends (last 30 days)
        daily_transactions = []
        for i in range(30):
            date = today - timedelta(days=i)
            count = Transaction.query.filter(
                Transaction.client_id == client_id,
                db.func.date(Transaction.created_at) == date,
            ).count()
            daily_transactions.append(
                {"date": date.strftime("%Y-%m-%d"), "count": count}
            )
        daily_transactions.reverse()

        # Service usage breakdown
        service_usage = (
            db.session.query(
                Service.name,
                Service.display_name,
                db.func.count(Transaction.id).label("count"),
                db.func.sum(Transaction.amount).label("revenue"),
            )
            .join(Transaction, Service.id == Transaction.service_id)
            .filter(
                Transaction.client_id == client_id,
                db.func.date(Transaction.created_at) >= last_30_days,
            )
            .group_by(Service.id, Service.name, Service.display_name)
            .all()
        )

        # Recent transactions
        recent_transactions = (
            Transaction.query.filter_by(client_id=client_id)
            .order_by(Transaction.created_at.desc())
            .limit(10)
            .all()
        )

        # Status breakdown
        status_breakdown = (
            db.session.query(
                Transaction.status, db.func.count(Transaction.id).label("count")
            )
            .filter(
                Transaction.client_id == client_id,
                db.func.date(Transaction.created_at) >= last_30_days,
            )
            .group_by(Transaction.status)
            .all()
        )

        return render_template(
            "admin/view_client.html",
            client=client,
            services=services,
            client_services=client_services,
            # Performance data
            total_transactions=total_transactions,
            last_30d_transactions=last_30d_transactions,
            last_7d_transactions=last_7d_transactions,
            success_rate_30d=round(success_rate_30d, 1),
            revenue_30d=revenue_30d,
            revenue_7d=revenue_7d,
            daily_transactions=daily_transactions,
            service_usage=service_usage,
            recent_transactions=recent_transactions,
            status_breakdown=status_breakdown,
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
    """List all transactions with advanced filtering"""
    try:
        from datetime import datetime

        # Get filter parameters
        page = request.args.get("page", 1, type=int)
        per_page = request.args.get("per_page", 50, type=int)

        # Date range filters
        start_date = request.args.get("start_date")
        end_date = request.args.get("end_date")

        # Filter parameters
        client_id = request.args.get("client_id", type=int)
        service_id = request.args.get("service_id", type=int)
        status = request.args.get("status")
        amount_min = request.args.get("amount_min", type=float)
        amount_max = request.args.get("amount_max", type=float)

        # Search parameters
        search = request.args.get("search", "").strip()
        search_type = request.args.get("search_type", "all")

        # Sort parameters
        sort_by = request.args.get("sort_by", "created_at")
        sort_order = request.args.get("sort_order", "desc")

        # Build query
        query = Transaction.query

        # Apply date filters
        if start_date:
            try:
                start_datetime = datetime.strptime(start_date, "%Y-%m-%d")
                query = query.filter(Transaction.created_at >= start_datetime)
            except ValueError:
                pass

        if end_date:
            try:
                end_datetime = datetime.strptime(end_date, "%Y-%m-%d")
                # Add one day to include the entire end date
                from datetime import timedelta

                end_datetime = end_datetime + timedelta(days=1)
                query = query.filter(Transaction.created_at < end_datetime)
            except ValueError:
                pass

        # Apply client filter
        if client_id:
            query = query.filter(Transaction.client_id == client_id)

        # Apply service filter
        if service_id:
            query = query.filter(Transaction.service_id == service_id)

        # Apply status filter
        if status:
            query = query.filter(Transaction.status == status)

        # Apply amount filters
        if amount_min is not None:
            query = query.filter(Transaction.amount >= amount_min)
        if amount_max is not None:
            query = query.filter(Transaction.amount <= amount_max)

        # Apply search filters
        if search:
            if search_type == "transaction_id":
                query = query.filter(Transaction.unique_id.ilike(f"%{search}%"))
            elif search_type == "client_name":
                query = query.join(Client).filter(
                    Client.company_name.ilike(f"%{search}%")
                )
            elif search_type == "mobile_number":
                query = query.filter(Transaction.mobile_number.ilike(f"%{search}%"))
            else:  # search all
                query = query.filter(
                    db.or_(
                        Transaction.unique_id.ilike(f"%{search}%"),
                        Transaction.mobile_number.ilike(f"%{search}%"),
                        Client.company_name.ilike(f"%{search}%"),
                    )
                ).join(Client)

        # Apply sorting
        if sort_by == "amount":
            sort_column = Transaction.amount
        elif sort_by == "status":
            sort_column = Transaction.status
        elif sort_by == "client":
            sort_column = Client.company_name
            query = query.join(Client)
        else:  # default to created_at
            sort_column = Transaction.created_at

        if sort_order == "asc":
            query = query.order_by(sort_column.asc())
        else:
            query = query.order_by(sort_column.desc())

        # Paginate results
        transactions = query.paginate(page=page, per_page=per_page, error_out=False)

        # Get filter options for dropdowns
        clients = (
            Client.query.filter_by(is_active=True).order_by(Client.company_name).all()
        )
        services = Service.query.order_by(Service.display_name).all()

        # Get unique statuses
        statuses = db.session.query(Transaction.status).distinct().all()
        status_options = [status[0] for status in statuses if status[0]]

        # Handle CSV export
        if request.args.get("export") == "csv":
            import csv
            import io
            from flask import make_response

            output = io.StringIO()
            writer = csv.writer(output)

            # Write header
            writer.writerow(
                [
                    "Unique ID",
                    "Client",
                    "Service",
                    "Status",
                    "Amount",
                    "Mobile Number",
                    "Created At",
                    "Updated At",
                ]
            )

            # Write data
            for transaction in transactions.items:
                writer.writerow(
                    [
                        transaction.unique_id,
                        transaction.client.company_name,
                        transaction.service.display_name,
                        transaction.status,
                        transaction.amount or "",
                        transaction.mobile_number or "",
                        transaction.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                        (
                            transaction.updated_at.strftime("%Y-%m-%d %H:%M:%S")
                            if transaction.updated_at
                            else ""
                        ),
                    ]
                )

            output.seek(0)
            response = make_response(output.getvalue())
            response.headers["Content-Type"] = "text/csv"
            response.headers["Content-Disposition"] = (
                f'attachment; filename=transactions_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
            )
            return response

        return render_template(
            "admin/transactions.html",
            transactions=transactions,
            clients=clients,
            services=services,
            status_options=status_options,
            # Pass current filter values to maintain state
            current_filters={
                "start_date": start_date,
                "end_date": end_date,
                "client_id": client_id,
                "service_id": service_id,
                "status": status,
                "amount_min": amount_min,
                "amount_max": amount_max,
                "search": search,
                "search_type": search_type,
                "sort_by": sort_by,
                "sort_order": sort_order,
                "per_page": per_page,
            },
        )
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


@admin.route("/api/clients/<int:client_id>/transactions")
@admin_required
def client_transactions_api(client_id):
    """API endpoint for client transactions with filtering and pagination"""
    try:
        from datetime import datetime

        # Get filter parameters
        page = request.args.get("page", 1, type=int)
        per_page = request.args.get("per_page", 25, type=int)

        # Date range filters
        start_date = request.args.get("start_date")
        end_date = request.args.get("end_date")

        # Filter parameters
        service_id = request.args.get("service_id", type=int)
        status = request.args.get("status")
        amount_min = request.args.get("amount_min", type=float)
        amount_max = request.args.get("amount_max", type=float)

        # Search parameters
        search = request.args.get("search", "").strip()

        # Sort parameters
        sort_by = request.args.get("sort_by", "created_at")
        sort_order = request.args.get("sort_order", "desc")

        # Build query for this specific client
        query = Transaction.query.filter_by(client_id=client_id)

        # Apply date filters
        if start_date:
            try:
                start_datetime = datetime.strptime(start_date, "%Y-%m-%d")
                query = query.filter(Transaction.created_at >= start_datetime)
            except ValueError:
                pass

        if end_date:
            try:
                end_datetime = datetime.strptime(end_date, "%Y-%m-%d")
                from datetime import timedelta

                end_datetime = end_datetime + timedelta(days=1)
                query = query.filter(Transaction.created_at < end_datetime)
            except ValueError:
                pass

        # Apply service filter
        if service_id:
            query = query.filter(Transaction.service_id == service_id)

        # Apply status filter
        if status:
            query = query.filter(Transaction.status == status)

        # Apply amount filters
        if amount_min is not None:
            query = query.filter(Transaction.amount >= amount_min)
        if amount_max is not None:
            query = query.filter(Transaction.amount <= amount_max)

        # Apply search filters
        if search:
            query = query.filter(Transaction.unique_id.ilike(f"%{search}%"))

        # Apply sorting
        if sort_by == "amount":
            sort_column = Transaction.amount
        elif sort_by == "status":
            sort_column = Transaction.status
        elif sort_by == "service":
            sort_column = Service.display_name
            query = query.join(Service)
        else:  # default to created_at
            sort_column = Transaction.created_at

        if sort_order == "asc":
            query = query.order_by(sort_column.asc())
        else:
            query = query.order_by(sort_column.desc())

        # Handle CSV export
        if request.args.get("export") == "csv":
            import csv
            import io
            from flask import make_response

            # Get all transactions for export (no pagination)
            all_transactions = query.all()

            output = io.StringIO()
            writer = csv.writer(output)

            # Write header
            writer.writerow(
                [
                    "Transaction ID",
                    "Service",
                    "Status",
                    "Amount",
                    "Mobile Number",
                    "Created At",
                    "Updated At",
                ]
            )

            # Write data
            for transaction in all_transactions:
                writer.writerow(
                    [
                        transaction.unique_id,
                        transaction.service.display_name,
                        transaction.status,
                        transaction.amount or "",
                        transaction.mobile_number or "",
                        transaction.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                        (
                            transaction.updated_at.strftime("%Y-%m-%d %H:%M:%S")
                            if transaction.updated_at
                            else ""
                        ),
                    ]
                )

            output.seek(0)
            response = make_response(output.getvalue())
            response.headers["Content-Type"] = "text/csv"
            response.headers["Content-Disposition"] = (
                f'attachment; filename=client_{client_id}_transactions_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
            )
            return response

        # Paginate results
        transactions = query.paginate(page=page, per_page=per_page, error_out=False)

        # Return JSON response
        return jsonify(
            {
                "transactions": [
                    {
                        "id": t.id,
                        "unique_id": t.unique_id,
                        "service_name": t.service.display_name,
                        "status": t.status,
                        "amount": float(t.amount) if t.amount else None,
                        "mobile_number": t.mobile_number,
                        "created_at": t.created_at.isoformat(),
                        "updated_at": (
                            t.updated_at.isoformat() if t.updated_at else None
                        ),
                    }
                    for t in transactions.items
                ],
                "pagination": {
                    "page": transactions.page,
                    "pages": transactions.pages,
                    "per_page": transactions.per_page,
                    "total": transactions.total,
                    "has_prev": transactions.has_prev,
                    "has_next": transactions.has_next,
                    "prev_num": transactions.prev_num,
                    "next_num": transactions.next_num,
                },
            }
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# Alert Management
@admin.route("/alerts")
@admin_required
def alerts():
    """List all alerts with filtering"""
    try:
        from datetime import datetime, timedelta

        page = request.args.get("page", 1, type=int)
        per_page = request.args.get("per_page", 25, type=int)

        # Filter parameters
        status = request.args.get("status", "")
        severity = request.args.get("severity", "")
        alert_type = request.args.get("alert_type", "")
        client_id = request.args.get("client_id", type=int)

        # Build query
        query = Alert.query

        if status:
            query = query.filter(Alert.status == status)
        if severity:
            query = query.filter(Alert.severity == severity)
        if alert_type:
            query = query.filter(Alert.alert_type == alert_type)
        if client_id:
            query = query.filter(Alert.client_id == client_id)

        # Order by creation date (newest first)
        query = query.order_by(Alert.created_at.desc())

        # Paginate results
        alerts = query.paginate(page=page, per_page=per_page, error_out=False)

        # Get filter options
        clients = (
            Client.query.filter_by(is_active=True).order_by(Client.company_name).all()
        )

        return render_template(
            "admin/alerts.html",
            alerts=alerts,
            clients=clients,
            current_filters={
                "status": status,
                "severity": severity,
                "alert_type": alert_type,
                "client_id": client_id,
                "per_page": per_page,
            },
        )

    except Exception as e:
        flash(f"Error loading alerts: {str(e)}", "error")
        return redirect(url_for("admin.dashboard"))


@admin.route("/alerts/<int:alert_id>/acknowledge", methods=["POST"])
@admin_required
def acknowledge_alert(alert_id):
    """Acknowledge an alert"""
    try:
        from alert_monitor import alert_monitor

        user_id = session.get("user_id")
        if alert_monitor.acknowledge_alert(alert_id, user_id):
            flash("Alert acknowledged successfully", "success")
        else:
            flash("Error acknowledging alert", "error")

    except Exception as e:
        flash(f"Error acknowledging alert: {str(e)}", "error")

    return redirect(url_for("admin.alerts"))


@admin.route("/alerts/<int:alert_id>/resolve", methods=["POST"])
@admin_required
def resolve_alert(alert_id):
    """Resolve an alert"""
    try:
        from alert_monitor import alert_monitor

        user_id = session.get("user_id")
        if alert_monitor.resolve_alert(alert_id, user_id):
            flash("Alert resolved successfully", "success")
        else:
            flash("Error resolving alert", "error")

    except Exception as e:
        flash(f"Error resolving alert: {str(e)}", "error")

    return redirect(url_for("admin.alerts"))


@admin.route("/alert-rules")
@admin_required
def alert_rules():
    """List all alert rules"""
    try:
        page = request.args.get("page", 1, type=int)
        rules = AlertRule.query.order_by(AlertRule.created_at.desc()).paginate(
            page=page, per_page=20, error_out=False
        )

        clients = (
            Client.query.filter_by(is_active=True).order_by(Client.company_name).all()
        )

        return render_template("admin/alert_rules.html", rules=rules, clients=clients)

    except Exception as e:
        flash(f"Error loading alert rules: {str(e)}", "error")
        return redirect(url_for("admin.dashboard"))


@admin.route("/alert-rules/new", methods=["GET", "POST"])
@admin_required
def new_alert_rule():
    """Create new alert rule"""
    if request.method == "POST":
        try:
            rule = AlertRule(
                name=request.form.get("name"),
                description=request.form.get("description"),
                alert_type=request.form.get("alert_type"),
                metric=request.form.get("metric"),
                threshold_value=float(request.form.get("threshold_value")),
                threshold_operator=request.form.get("threshold_operator"),
                time_window=int(request.form.get("time_window")),
                is_active=bool(request.form.get("is_active")),
                client_id=(
                    int(request.form.get("client_id"))
                    if request.form.get("client_id")
                    else None
                ),
            )

            db.session.add(rule)
            db.session.commit()

            flash("Alert rule created successfully", "success")
            return redirect(url_for("admin.alert_rules"))

        except Exception as e:
            flash(f"Error creating alert rule: {str(e)}", "error")

    clients = Client.query.filter_by(is_active=True).order_by(Client.company_name).all()
    return render_template("admin/new_alert_rule.html", clients=clients)


@admin.route("/alert-rules/<int:rule_id>/edit", methods=["GET", "POST"])
@admin_required
def edit_alert_rule(rule_id):
    """Edit alert rule"""
    rule = AlertRule.query.get_or_404(rule_id)

    if request.method == "POST":
        try:
            rule.name = request.form.get("name")
            rule.description = request.form.get("description")
            rule.alert_type = request.form.get("alert_type")
            rule.metric = request.form.get("metric")
            rule.threshold_value = float(request.form.get("threshold_value"))
            rule.threshold_operator = request.form.get("threshold_operator")
            rule.time_window = int(request.form.get("time_window"))
            rule.is_active = bool(request.form.get("is_active"))
            rule.client_id = (
                int(request.form.get("client_id"))
                if request.form.get("client_id")
                else None
            )

            db.session.commit()

            flash("Alert rule updated successfully", "success")
            return redirect(url_for("admin.alert_rules"))

        except Exception as e:
            flash(f"Error updating alert rule: {str(e)}", "error")

    clients = Client.query.filter_by(is_active=True).order_by(Client.company_name).all()
    return render_template("admin/edit_alert_rule.html", rule=rule, clients=clients)


@admin.route("/alert-rules/<int:rule_id>/delete", methods=["POST"])
@admin_required
def delete_alert_rule(rule_id):
    """Delete alert rule"""
    try:
        rule = AlertRule.query.get_or_404(rule_id)
        db.session.delete(rule)
        db.session.commit()

        flash("Alert rule deleted successfully", "success")

    except Exception as e:
        flash(f"Error deleting alert rule: {str(e)}", "error")

    return redirect(url_for("admin.alert_rules"))


@admin.route("/monitoring/check-alerts", methods=["POST"])
@admin_required
def check_alerts():
    """Manually trigger alert checking"""
    try:
        from alert_monitor import alert_monitor

        alerts_created = alert_monitor.check_all_rules()

        if alerts_created:
            flash(
                f"Alert check completed. {len(alerts_created)} new alerts created.",
                "success",
            )
        else:
            flash("Alert check completed. No new alerts created.", "info")

    except Exception as e:
        flash(f"Error checking alerts: {str(e)}", "error")

    return redirect(url_for("admin.alerts"))


# Test route for debugging
@admin.route("/test-export")
@admin_required
def test_export():
    """Test route to check export functionality"""
    try:
        # Test basic queries
        clients_count = Client.query.count()
        transactions_count = Transaction.query.count()
        
        return jsonify({
            'clients_count': clients_count,
            'transactions_count': transactions_count,
            'message': 'Export test successful'
        })
    except Exception as e:
        return jsonify({
            'error': str(e),
            'message': 'Export test failed'
        }), 500


# Bulk Export & Reporting
@admin.route("/bulk-export")
@admin_required
def bulk_export():
    """Bulk export interface for multiple clients"""
    try:
        clients = Client.query.filter_by(is_active=True).order_by(Client.company_name).all()
        services = Service.query.order_by(Service.display_name).all()
        
        # Get unique statuses
        statuses = db.session.query(Transaction.status).distinct().all()
        status_options = [status[0] for status in statuses if status[0]]
        
        return render_template("admin/bulk_export.html", 
                             clients=clients, 
                             services=services, 
                             status_options=status_options)
        
    except Exception as e:
        flash(f"Error loading bulk export page: {str(e)}", "error")
        return redirect(url_for("admin.dashboard"))


@admin.route("/bulk-export/transactions", methods=["POST"])
@admin_required
def bulk_export_transactions():
    """Export transactions for multiple clients"""
    try:
        print("[BULK EXPORT] Starting export function...")
        
        from datetime import datetime, timedelta
        import csv
        import io
        from flask import make_response
        
        print("[BULK EXPORT] Imports successful...")
        
        # Debug logging
        print(f"[BULK EXPORT] Form data received: {request.form}")
        print(f"[BULK EXPORT] Request method: {request.method}")
        print(f"[BULK EXPORT] Request URL: {request.url}")
        
        # Get export parameters
        print("[BULK EXPORT] Getting form parameters...")
        client_ids = request.form.getlist("client_ids")
        service_ids = request.form.getlist("service_ids")
        statuses = request.form.getlist("statuses")
        start_date = request.form.get("start_date")
        end_date = request.form.get("end_date")
        export_format = request.form.get("export_format", "csv")
        
        # Convert string IDs to integers
        try:
            client_ids = [int(cid) for cid in client_ids if cid]
            service_ids = [int(sid) for sid in service_ids if sid]
        except ValueError as e:
            print(f"[BULK EXPORT] Error converting IDs to integers: {e}")
            flash("Invalid client or service ID format", "error")
            return redirect(url_for("admin.bulk_export"))
        
        print(f"[BULK EXPORT] Parameters: client_ids={client_ids}, service_ids={service_ids}, statuses={statuses}, start_date={start_date}, end_date={end_date}")
        
        # Build query
        print("[BULK EXPORT] Building query...")
        query = Transaction.query
        
        # Apply client filter
        if client_ids:
            print(f"[BULK EXPORT] Applying client filter: {client_ids}")
            query = query.filter(Transaction.client_id.in_(client_ids))
        
        # Apply service filter
        if service_ids:
            print(f"[BULK EXPORT] Applying service filter: {service_ids}")
            query = query.filter(Transaction.service_id.in_(service_ids))
        
        # Apply status filter
        if statuses:
            print(f"[BULK EXPORT] Applying status filter: {statuses}")
            query = query.filter(Transaction.status.in_(statuses))
        
        # Apply date filters
        if start_date:
            try:
                start_datetime = datetime.strptime(start_date, "%Y-%m-%d")
                print(f"[BULK EXPORT] Applying start date filter: {start_datetime}")
                query = query.filter(Transaction.created_at >= start_datetime)
            except ValueError as e:
                print(f"[BULK EXPORT] Error parsing start date: {e}")
                pass
        
        if end_date:
            try:
                end_datetime = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
                print(f"[BULK EXPORT] Applying end date filter: {end_datetime}")
                query = query.filter(Transaction.created_at < end_datetime)
            except ValueError as e:
                print(f"[BULK EXPORT] Error parsing end date: {e}")
                pass
        
        # Order by creation date
        print("[BULK EXPORT] Applying order by...")
        query = query.order_by(Transaction.created_at.desc())
        
        # Get all transactions
        print("[BULK EXPORT] Executing query...")
        transactions = query.all()
        print(f"[BULK EXPORT] Found {len(transactions)} transactions to export")
        
        if export_format == "csv":
            print("[BULK EXPORT] Calling CSV export function...")
            return _export_transactions_csv(transactions, client_ids, start_date, end_date)
        elif export_format == "pdf":
            print("[BULK EXPORT] Calling PDF export function...")
            return _export_transactions_pdf(transactions, client_ids, start_date, end_date)
        else:
            print(f"[BULK EXPORT] Unsupported export format: {export_format}")
            flash("Unsupported export format", "error")
            return redirect(url_for("admin.bulk_export"))
            
    except Exception as e:
        import traceback
        print(f"[BULK EXPORT] ERROR: {str(e)}")
        print(f"[BULK EXPORT] Traceback: {traceback.format_exc()}")
        flash(f"Error exporting transactions: {str(e)}", "error")
        return redirect(url_for("admin.bulk_export"))


def _export_transactions_csv(transactions, client_ids, start_date, end_date):
    """Helper function to export transactions as CSV"""
    try:
        import csv
        import io
        from flask import make_response
        from datetime import datetime
        
        print(f"[CSV EXPORT] Starting CSV export for {len(transactions)} transactions")
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow([
            'Transaction ID', 'Client', 'Service', 'Status', 'Amount', 
            'Mobile Number', 'Created At', 'Updated At', 'Client App ID'
        ])
        
        # Write data
        for transaction in transactions:
            try:
                writer.writerow([
                    transaction.unique_id or '',
                    transaction.client.company_name if transaction.client else 'Unknown Client',
                    transaction.service.display_name if transaction.service else 'Unknown Service',
                    transaction.status or '',
                    transaction.amount or '',
                    transaction.mobile_number or '',
                    transaction.created_at.strftime('%Y-%m-%d %H:%M:%S') if transaction.created_at else '',
                    transaction.updated_at.strftime('%Y-%m-%d %H:%M:%S') if transaction.updated_at else '',
                    transaction.client.app_id if transaction.client else ''
                ])
            except Exception as e:
                print(f"[CSV EXPORT] Error writing transaction {transaction.id}: {str(e)}")
                # Write a row with error info
                writer.writerow([
                    transaction.unique_id or 'ERROR',
                    'ERROR',
                    'ERROR', 
                    'ERROR',
                    'ERROR',
                    'ERROR',
                    'ERROR',
                    'ERROR',
                    'ERROR'
                ])
        
        output.seek(0)
        csv_content = output.getvalue()
        print(f"[CSV EXPORT] Generated CSV content length: {len(csv_content)}")
        
        response = make_response(csv_content)
        response.headers['Content-Type'] = 'text/csv'
        
        # Generate filename
        filename_parts = ['transactions_export']
        if client_ids and len(client_ids) == 1:
            client = Client.query.get(client_ids[0])
            if client:
                filename_parts.append(client.company_name.replace(' ', '_'))
        elif len(client_ids) > 1:
            filename_parts.append(f'{len(client_ids)}_clients')
        
        if start_date:
            filename_parts.append(f'from_{start_date}')
        if end_date:
            filename_parts.append(f'to_{end_date}')
        
        filename_parts.append(datetime.now().strftime('%Y%m%d_%H%M%S'))
        filename = '_'.join(filename_parts) + '.csv'
        
        response.headers['Content-Disposition'] = f'attachment; filename={filename}'
        print(f"[CSV EXPORT] Returning response with filename: {filename}")
        return response
        
    except Exception as e:
        import traceback
        print(f"[CSV EXPORT] ERROR: {str(e)}")
        print(f"[CSV EXPORT] Traceback: {traceback.format_exc()}")
        from flask import make_response
        return make_response(f"Error generating CSV: {str(e)}", 500)


def _export_transactions_pdf(transactions, client_ids, start_date, end_date):
    """Helper function to export transactions as PDF"""
    try:
        from pdf_utils import PDFGenerator, create_pdf_response
        from datetime import datetime
        
        print(f"[PDF EXPORT] Starting PDF export for {len(transactions)} transactions")
        
        # Generate PDF
        pdf_generator = PDFGenerator()
        pdf_buffer = pdf_generator.create_transactions_pdf(transactions, client_ids, start_date, end_date)
        
        # Generate filename
        filename_parts = ['transactions_report']
        if client_ids and len(client_ids) == 1:
            client = Client.query.get(client_ids[0])
            if client:
                filename_parts.append(client.company_name.replace(' ', '_'))
        elif len(client_ids) > 1:
            filename_parts.append(f'{len(client_ids)}_clients')
        
        if start_date:
            filename_parts.append(f'from_{start_date}')
        if end_date:
            filename_parts.append(f'to_{end_date}')
        
        filename_parts.append(datetime.now().strftime('%Y%m%d_%H%M%S'))
        filename = '_'.join(filename_parts) + '.pdf'
        
        print(f"[PDF EXPORT] Returning PDF response with filename: {filename}")
        return create_pdf_response(pdf_buffer, filename)
        
    except Exception as e:
        import traceback
        print(f"[PDF EXPORT] ERROR: {str(e)}")
        print(f"[PDF EXPORT] Traceback: {traceback.format_exc()}")
        from flask import make_response
        return make_response(f"Error generating PDF: {str(e)}", 500)


@admin.route("/bulk-export/clients")
@admin_required
def bulk_export_clients():
    """Export client data with performance metrics"""
    try:
        from datetime import datetime, timedelta
        import csv
        import io
        from flask import make_response
        
        print("[CLIENT EXPORT] Starting client export")
        print(f"[CLIENT EXPORT] Request method: {request.method}")
        print(f"[CLIENT EXPORT] Request URL: {request.url}")
        
        # Get all active clients
        print("[CLIENT EXPORT] Querying active clients...")
        clients = Client.query.filter_by(is_active=True).order_by(Client.company_name).all()
        print(f"[CLIENT EXPORT] Found {len(clients)} active clients")
        
        # Calculate performance metrics for each client
        today = datetime.now().date()
        last_30_days = today - timedelta(days=30)
        last_7_days = today - timedelta(days=7)
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow([
            'Client ID', 'Company Name', 'Contact Person', 'Email', 'Phone',
            'App ID', 'API Username', 'Is Active', 'Created At',
            'Total Transactions', 'Last 30d Transactions', 'Last 7d Transactions',
            'Success Rate (30d)', 'Revenue (30d)', 'Last Transaction Date',
            'Callback URL'
        ])
        
        # Write data
        print("[CLIENT EXPORT] Processing clients...")
        for i, client in enumerate(clients):
            print(f"[CLIENT EXPORT] Processing client {i+1}/{len(clients)}: {client.company_name}")
            
            try:
                # Get transaction counts
                total_transactions = Transaction.query.filter_by(client_id=client.id).count()
                last_30d_transactions = Transaction.query.filter(
                    Transaction.client_id == client.id,
                    db.func.date(Transaction.created_at) >= last_30_days
                ).count()
                last_7d_transactions = Transaction.query.filter(
                    Transaction.client_id == client.id,
                    db.func.date(Transaction.created_at) >= last_7_days
                ).count()
                
                # Get success rate (last 30 days)
                successful_transactions = Transaction.query.filter(
                    Transaction.client_id == client.id,
                    db.func.date(Transaction.created_at) >= last_30_days,
                    Transaction.status == 'completed'
                ).count()
                
                success_rate = (successful_transactions / last_30d_transactions * 100) if last_30d_transactions > 0 else 0
                
                # Get revenue (last 30 days)
                revenue_30d = db.session.query(db.func.sum(Transaction.amount)).filter(
                    Transaction.client_id == client.id,
                    db.func.date(Transaction.created_at) >= last_30_days,
                    Transaction.status == 'completed'
                ).scalar() or 0
                
                # Get last transaction date
                last_transaction = Transaction.query.filter_by(client_id=client.id).order_by(
                    Transaction.created_at.desc()
                ).first()
                
                writer.writerow([
                    client.id,
                    client.company_name,
                    client.contact_person,
                    client.email,
                    client.phone,
                    client.app_id,
                    client.api_username,
                    'Yes' if client.is_active else 'No',
                    client.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                    total_transactions,
                    last_30d_transactions,
                    last_7d_transactions,
                    f"{success_rate:.1f}%",
                    f"${revenue_30d:.2f}",
                    last_transaction.created_at.strftime('%Y-%m-%d %H:%M:%S') if last_transaction else '',
                    client.callback_url or ''
                ])
                
            except Exception as e:
                print(f"[CLIENT EXPORT] Error processing client {client.company_name}: {str(e)}")
                # Write a row with error info
                writer.writerow([
                    client.id,
                    client.company_name,
                    'ERROR',
                    'ERROR',
                    'ERROR',
                    'ERROR',
                    'ERROR',
                    'ERROR',
                    'ERROR',
                    'ERROR',
                    'ERROR',
                    'ERROR',
                    'ERROR',
                    'ERROR',
                    'ERROR',
                    'ERROR'
                ])
        
        output.seek(0)
        csv_content = output.getvalue()
        print(f"[CLIENT EXPORT] Generated CSV content length: {len(csv_content)}")
        
        response = make_response(csv_content)
        response.headers['Content-Type'] = 'text/csv'
        filename = f'clients_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        response.headers['Content-Disposition'] = f'attachment; filename={filename}'
        
        print(f"[CLIENT EXPORT] Returning response with filename: {filename}")
        return response
        
    except Exception as e:
        import traceback
        print(f"[CLIENT EXPORT] ERROR: {str(e)}")
        print(f"[CLIENT EXPORT] Traceback: {traceback.format_exc()}")
        flash(f"Error exporting clients: {str(e)}", "error")
        return redirect(url_for("admin.bulk_export"))


@admin.route("/bulk-export/clients/pdf")
@admin_required
def bulk_export_clients_pdf():
    """Export client data as PDF with performance metrics"""
    try:
        from datetime import datetime, timedelta
        from pdf_utils import PDFGenerator, create_pdf_response
        
        print("[CLIENT PDF EXPORT] Starting client PDF export")
        
        # Get all active clients
        print("[CLIENT PDF EXPORT] Querying active clients...")
        clients = Client.query.filter_by(is_active=True).order_by(Client.company_name).all()
        print(f"[CLIENT PDF EXPORT] Found {len(clients)} active clients")
        
        # Calculate performance metrics for each client
        today = datetime.now().date()
        last_30_days = today - timedelta(days=30)
        last_7_days = today - timedelta(days=7)
        
        clients_data = []
        print("[CLIENT PDF EXPORT] Processing clients...")
        
        for i, client in enumerate(clients):
            print(f"[CLIENT PDF EXPORT] Processing client {i+1}/{len(clients)}: {client.company_name}")
            
            try:
                # Get transaction counts
                total_transactions = Transaction.query.filter_by(client_id=client.id).count()
                last_30d_transactions = Transaction.query.filter(
                    Transaction.client_id == client.id,
                    db.func.date(Transaction.created_at) >= last_30_days
                ).count()
                last_7d_transactions = Transaction.query.filter(
                    Transaction.client_id == client.id,
                    db.func.date(Transaction.created_at) >= last_7_days
                ).count()
                
                # Get success rate (last 30 days)
                successful_transactions = Transaction.query.filter(
                    Transaction.client_id == client.id,
                    db.func.date(Transaction.created_at) >= last_30_days,
                    Transaction.status == 'completed'
                ).count()
                
                success_rate = (successful_transactions / last_30d_transactions * 100) if last_30d_transactions > 0 else 0
                
                # Get revenue (last 30 days)
                revenue_30d = db.session.query(db.func.sum(Transaction.amount)).filter(
                    Transaction.client_id == client.id,
                    db.func.date(Transaction.created_at) >= last_30_days,
                    Transaction.status == 'completed'
                ).scalar() or 0
                
                clients_data.append({
                    'company_name': client.company_name,
                    'contact_person': client.contact_person,
                    'email': client.email,
                    'phone': client.phone,
                    'is_active': client.is_active,
                    'total_transactions': total_transactions,
                    'last_30d_transactions': last_30d_transactions,
                    'last_7d_transactions': last_7d_transactions,
                    'success_rate': success_rate,
                    'revenue_30d': revenue_30d
                })
                
            except Exception as e:
                print(f"[CLIENT PDF EXPORT] Error processing client {client.company_name}: {str(e)}")
                # Add client with error data
                clients_data.append({
                    'company_name': client.company_name,
                    'contact_person': 'ERROR',
                    'email': 'ERROR',
                    'phone': 'ERROR',
                    'is_active': False,
                    'total_transactions': 0,
                    'last_30d_transactions': 0,
                    'last_7d_transactions': 0,
                    'success_rate': 0,
                    'revenue_30d': 0
                })
        
        # Generate PDF
        print("[CLIENT PDF EXPORT] Generating PDF...")
        pdf_generator = PDFGenerator()
        pdf_buffer = pdf_generator.create_clients_pdf(clients_data)
        
        # Generate filename
        filename = f'clients_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf'
        
        print(f"[CLIENT PDF EXPORT] Returning PDF response with filename: {filename}")
        return create_pdf_response(pdf_buffer, filename)
        
    except Exception as e:
        import traceback
        print(f"[CLIENT PDF EXPORT] ERROR: {str(e)}")
        print(f"[CLIENT PDF EXPORT] Traceback: {traceback.format_exc()}")
        flash(f"Error exporting clients PDF: {str(e)}", "error")
        return redirect(url_for("admin.bulk_export"))


@admin.route("/monitoring/dashboard")
@admin_required
def monitoring_dashboard():
    """Centralized monitoring dashboard for all clients"""
    try:
        from datetime import datetime, timedelta
        
        print("[MONITORING] Loading centralized monitoring dashboard...")
        
        # Get all clients with their current status
        clients = Client.query.filter_by(is_active=True).order_by(Client.company_name).all()
        print(f"[MONITORING] Found {len(clients)} active clients")
        
        # Calculate real-time metrics
        today = datetime.now().date()
        last_24h = datetime.now() - timedelta(hours=24)
        last_7d = today - timedelta(days=7)
        last_30d = today - timedelta(days=30)
        
        # System-wide statistics
        total_transactions = Transaction.query.count()
        today_transactions = Transaction.query.filter(
            db.func.date(Transaction.created_at) == today
        ).count()
        last_24h_transactions = Transaction.query.filter(
            Transaction.created_at >= last_24h
        ).count()
        
        # Success rates
        completed_today = Transaction.query.filter(
            db.func.date(Transaction.created_at) == today,
            Transaction.status == 'completed'
        ).count()
        success_rate_today = (completed_today / today_transactions * 100) if today_transactions > 0 else 0
        
        # Revenue metrics
        today_revenue = db.session.query(db.func.sum(Transaction.amount)).filter(
            db.func.date(Transaction.created_at) == today,
            Transaction.status == 'completed'
        ).scalar() or 0
        
        last_30d_revenue = db.session.query(db.func.sum(Transaction.amount)).filter(
            db.func.date(Transaction.created_at) >= last_30d,
            Transaction.status == 'completed'
        ).scalar() or 0
        
        # Client performance data for charts
        client_performance = []
        for client in clients:
            # Get client metrics
            client_transactions = Transaction.query.filter_by(client_id=client.id)
            total_client_txns = client_transactions.count()
            
            # Last 7 days performance
            last_7d_txns = client_transactions.filter(
                db.func.date(Transaction.created_at) >= last_7d
            ).count()
            
            # Success rate (last 7 days)
            successful_7d = client_transactions.filter(
                db.func.date(Transaction.created_at) >= last_7d,
                Transaction.status == 'completed'
            ).count()
            success_rate_7d = (successful_7d / last_7d_txns * 100) if last_7d_txns > 0 else 0
            
            # Revenue (last 7 days)
            revenue_7d = db.session.query(db.func.sum(Transaction.amount)).filter(
                Transaction.client_id == client.id,
                db.func.date(Transaction.created_at) >= last_7d,
                Transaction.status == 'completed'
            ).scalar() or 0
            
            # Last transaction
            last_transaction = client_transactions.order_by(
                Transaction.created_at.desc()
            ).first()
            
            # Determine client status
            if last_transaction:
                hours_since_last = (datetime.now() - last_transaction.created_at).total_seconds() / 3600
                if hours_since_last < 1:
                    status = "Very Active"
                    status_color = "success"
                elif hours_since_last < 24:
                    status = "Active"
                    status_color = "info"
                elif hours_since_last < 168:  # 7 days
                    status = "Moderate"
                    status_color = "warning"
                else:
                    status = "Inactive"
                    status_color = "danger"
            else:
                status = "No Activity"
                status_color = "secondary"
            
            client_performance.append({
                'id': client.id,
                'name': client.company_name,
                'app_id': client.app_id,
                'total_transactions': total_client_txns,
                'last_7d_transactions': last_7d_txns,
                'success_rate': success_rate_7d,
                'revenue_7d': revenue_7d,
                'status': status,
                'status_color': status_color,
                'last_transaction': last_transaction.created_at if last_transaction else None,
                'hours_since_last': hours_since_last if last_transaction else None
            })
        
        # Sort clients by activity (most recent first)
        client_performance.sort(key=lambda x: x['last_transaction'] or datetime.min, reverse=True)
        
        # Get recent alerts
        recent_alerts = Alert.query.filter_by(status='active').order_by(
            Alert.created_at.desc()
        ).limit(10).all()
        
        # Get alert statistics
        total_alerts = Alert.query.count()
        active_alerts = Alert.query.filter_by(status='active').count()
        critical_alerts = Alert.query.filter_by(severity='critical', status='active').count()
        warning_alerts = Alert.query.filter_by(severity='warning', status='active').count()
        
        # Transaction trends for charts (last 7 days)
        transaction_trends = []
        for i in range(7):
            date = today - timedelta(days=i)
            count = Transaction.query.filter(
                db.func.date(Transaction.created_at) == date
            ).count()
            transaction_trends.append({
                'date': date.strftime('%Y-%m-%d'),
                'count': count
            })
        transaction_trends.reverse()  # Show oldest to newest
        
        # Service usage statistics
        service_stats = db.session.query(
            Service.display_name,
            db.func.count(Transaction.id).label('count')
        ).join(Transaction).filter(
            db.func.date(Transaction.created_at) >= last_7d
        ).group_by(Service.id, Service.display_name).all()
        
        return render_template("admin/monitoring_dashboard.html",
                             clients=client_performance,
                             recent_alerts=recent_alerts,
                             current_user=current_user,
                             
                             # System metrics
                             total_transactions=total_transactions,
                             today_transactions=today_transactions,
                             last_24h_transactions=last_24h_transactions,
                             success_rate_today=success_rate_today,
                             today_revenue=today_revenue,
                             last_30d_revenue=last_30d_revenue,
                             
                             # Alert metrics
                             total_alerts=total_alerts,
                             active_alerts=active_alerts,
                             critical_alerts=critical_alerts,
                             warning_alerts=warning_alerts,
                             
                             # Chart data
                             transaction_trends=transaction_trends,
                             service_stats=service_stats)
        
    except Exception as e:
        import traceback
        print(f"[MONITORING] ERROR: {str(e)}")
        print(f"[MONITORING] Traceback: {traceback.format_exc()}")
        flash(f"Error loading monitoring dashboard: {str(e)}", "error")
        return redirect(url_for("admin.dashboard"))


@admin.route("/security/dashboard")
@admin_required
def security_dashboard():
    """Security monitoring dashboard"""
    try:
        from datetime import datetime, timedelta
        from security_monitor import security_monitor
        
        print("[SECURITY] Loading security monitoring dashboard...")
        
        # Get security summary for last 24 hours
        security_summary = security_monitor.get_security_summary(hours=24)
        
        # Get recent security events
        recent_events = SecurityEvent.query.order_by(
            SecurityEvent.created_at.desc()
        ).limit(20).all()
        
        # Get blocked IPs
        blocked_ips = IPBlacklist.query.filter_by(is_active=True).order_by(
            IPBlacklist.blocked_at.desc()
        ).limit(10).all()
        
        # Get rate limited identifiers
        rate_limited = RateLimit.query.filter_by(is_blocked=True).order_by(
            RateLimit.updated_at.desc()
        ).limit(10).all()
        
        # Get fraud alerts
        fraud_alerts = FraudDetection.query.filter(
            FraudDetection.status == 'pending'
        ).order_by(FraudDetection.created_at.desc()).limit(10).all()
        
        # Get security events for charts (last 7 days)
        chart_data = []
        for i in range(7):
            date = datetime.now().date() - timedelta(days=i)
            events_count = SecurityEvent.query.filter(
                db.func.date(SecurityEvent.created_at) == date
            ).count()
            chart_data.append({
                'date': date.strftime('%Y-%m-%d'),
                'count': events_count
            })
        chart_data.reverse()
        
        # Get events by type for pie chart
        event_types = db.session.query(
            SecurityEvent.event_type,
            db.func.count(SecurityEvent.id).label('count')
        ).filter(
            SecurityEvent.created_at >= datetime.utcnow() - timedelta(days=7)
        ).group_by(SecurityEvent.event_type).all()
        
        return render_template("admin/security_dashboard.html",
                             security_summary=security_summary,
                             recent_events=recent_events,
                             blocked_ips=blocked_ips,
                             rate_limited=rate_limited,
                             fraud_alerts=fraud_alerts,
                             chart_data=chart_data,
                             event_types=event_types,
                             current_user=current_user)
        
    except Exception as e:
        import traceback
        print(f"[SECURITY] ERROR: {str(e)}")
        print(f"[SECURITY] Traceback: {traceback.format_exc()}")
        flash(f"Error loading security dashboard: {str(e)}", "error")
        return redirect(url_for("admin.dashboard"))


@admin.route("/security/events")
@admin_required
def security_events():
    """Security events management page"""
    try:
        from datetime import datetime, timedelta
        
        # Get filter parameters
        event_type = request.args.get('event_type', '')
        severity = request.args.get('severity', '')
        status = request.args.get('status', '')
        page = request.args.get('page', 1, type=int)
        per_page = 20
        
        # Build query
        query = SecurityEvent.query
        
        if event_type:
            query = query.filter(SecurityEvent.event_type == event_type)
        if severity:
            query = query.filter(SecurityEvent.severity == severity)
        if status:
            query = query.filter(SecurityEvent.status == status)
        
        # Order by creation date
        query = query.order_by(SecurityEvent.created_at.desc())
        
        # Paginate
        events = query.paginate(
            page=page, per_page=per_page, error_out=False
        )
        
        # Get unique values for filters
        event_types = db.session.query(SecurityEvent.event_type).distinct().all()
        severities = db.session.query(SecurityEvent.severity).distinct().all()
        statuses = db.session.query(SecurityEvent.status).distinct().all()
        
        return render_template("admin/security_events.html",
                             events=events,
                             event_types=[t[0] for t in event_types],
                             severities=[s[0] for s in severities],
                             statuses=[st[0] for st in statuses],
                             current_user=current_user)
        
    except Exception as e:
        import traceback
        print(f"[SECURITY] ERROR: {str(e)}")
        print(f"[SECURITY] Traceback: {traceback.format_exc()}")
        flash(f"Error loading security events: {str(e)}", "error")
        return redirect(url_for("admin.dashboard"))


@admin.route("/security/block-ip", methods=["POST"])
@admin_required
def block_ip():
    """Block an IP address"""
    try:
        from security_monitor import security_monitor
        
        ip_address = request.form.get('ip_address')
        reason = request.form.get('reason')
        expires_hours = request.form.get('expires_hours', type=int)
        
        if not ip_address or not reason:
            flash("IP address and reason are required", "error")
            return redirect(url_for("admin.security_dashboard"))
        
        # Calculate expiration time
        expires_at = None
        if expires_hours and expires_hours > 0:
            expires_at = datetime.utcnow() + timedelta(hours=expires_hours)
        
        # Block the IP
        success, message = security_monitor.block_ip(
            ip_address=ip_address,
            reason=reason,
            blocked_by=current_user.id,
            expires_at=expires_at
        )
        
        if success:
            flash(f"IP {ip_address} blocked successfully", "success")
        else:
            flash(f"Failed to block IP: {message}", "error")
        
        return redirect(url_for("admin.security_dashboard"))
        
    except Exception as e:
        import traceback
        print(f"[SECURITY] ERROR: {str(e)}")
        print(f"[SECURITY] Traceback: {traceback.format_exc()}")
        flash(f"Error blocking IP: {str(e)}", "error")
        return redirect(url_for("admin.security_dashboard"))


@admin.route("/security/unblock-ip/<int:block_id>", methods=["POST"])
@admin_required
def unblock_ip(block_id):
    """Unblock an IP address"""
    try:
        block = IPBlacklist.query.get_or_404(block_id)
        block.is_active = False
        db.session.commit()
        
        flash(f"IP {block.ip_address} unblocked successfully", "success")
        return redirect(url_for("admin.security_dashboard"))
        
    except Exception as e:
        import traceback
        print(f"[SECURITY] ERROR: {str(e)}")
        print(f"[SECURITY] Traceback: {traceback.format_exc()}")
        flash(f"Error unblocking IP: {str(e)}", "error")
        return redirect(url_for("admin.security_dashboard"))


@admin.route("/security/resolve-event/<int:event_id>", methods=["POST"])
@admin_required
def resolve_security_event(event_id):
    """Resolve a security event"""
    try:
        event = SecurityEvent.query.get_or_404(event_id)
        event.status = 'resolved'
        event.resolved_at = datetime.utcnow()
        event.resolved_by = current_user.id
        db.session.commit()
        
        flash("Security event resolved successfully", "success")
        return redirect(url_for("admin.security_events"))
        
    except Exception as e:
        import traceback
        print(f"[SECURITY] ERROR: {str(e)}")
        print(f"[SECURITY] Traceback: {traceback.format_exc()}")
        flash(f"Error resolving event: {str(e)}", "error")
        return redirect(url_for("admin.security_events"))


@admin.route("/reports/performance-summary")
@admin_required
def performance_summary_report():
    """Generate performance summary report"""
    try:
        from datetime import datetime, timedelta
        
        # Get date range (default to last 30 days)
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=30)
        
        # Get all active clients
        clients = Client.query.filter_by(is_active=True).order_by(Client.company_name).all()
        
        # Calculate summary statistics
        total_clients = len(clients)
        total_transactions = Transaction.query.filter(
            db.func.date(Transaction.created_at) >= start_date
        ).count()
        
        successful_transactions = Transaction.query.filter(
            db.func.date(Transaction.created_at) >= start_date,
            Transaction.status == 'completed'
        ).count()
        
        overall_success_rate = (successful_transactions / total_transactions * 100) if total_transactions > 0 else 0
        
        total_revenue = db.session.query(db.func.sum(Transaction.amount)).filter(
            db.func.date(Transaction.created_at) >= start_date,
            Transaction.status == 'completed'
        ).scalar() or 0
        
        # Client performance data
        client_performance = []
        for client in clients:
            client_transactions = Transaction.query.filter(
                Transaction.client_id == client.id,
                db.func.date(Transaction.created_at) >= start_date
            ).count()
            
            client_successful = Transaction.query.filter(
                Transaction.client_id == client.id,
                db.func.date(Transaction.created_at) >= start_date,
                Transaction.status == 'completed'
            ).count()
            
            client_success_rate = (client_successful / client_transactions * 100) if client_transactions > 0 else 0
            
            client_revenue = db.session.query(db.func.sum(Transaction.amount)).filter(
                Transaction.client_id == client.id,
                db.func.date(Transaction.created_at) >= start_date,
                Transaction.status == 'completed'
            ).scalar() or 0
            
            client_performance.append({
                'client': client,
                'transactions': client_transactions,
                'success_rate': client_success_rate,
                'revenue': client_revenue
            })
        
        # Sort by revenue descending
        client_performance.sort(key=lambda x: x['revenue'], reverse=True)
        
        return render_template("admin/performance_summary_report.html",
                             start_date=start_date,
                             end_date=end_date,
                             total_clients=total_clients,
                             total_transactions=total_transactions,
                             overall_success_rate=overall_success_rate,
                             total_revenue=total_revenue,
                             client_performance=client_performance)
        
    except Exception as e:
        flash(f"Error generating performance summary: {str(e)}", "error")
        return redirect(url_for("admin.dashboard"))
