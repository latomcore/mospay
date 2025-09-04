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
            Transaction.created_at >= last_24h,
            Transaction.status == 'completed'
        ).count()
        
        success_rate = (successful_transactions / recent_transactions_count * 100) if recent_transactions_count > 0 else 0
        
        # Revenue calculations (assuming amount field exists)
        today_revenue = db.session.query(db.func.sum(Transaction.amount)).filter(
            db.func.date(Transaction.created_at) == today,
            Transaction.status == 'completed'
        ).scalar() or 0
        
        month_revenue = db.session.query(db.func.sum(Transaction.amount)).filter(
            db.func.date(Transaction.created_at) >= this_month,
            Transaction.status == 'completed'
        ).scalar() or 0
        
        # Transaction volume by service (for charts)
        service_stats = db.session.query(
            Service.name,
            Service.display_name,
            db.func.count(Transaction.id).label('count')
        ).join(Transaction, Service.id == Transaction.service_id).filter(
            Transaction.created_at >= last_24h
        ).group_by(Service.id, Service.name, Service.display_name).all()
        
        # Recent transactions
        recent_transactions = (
            Transaction.query.order_by(Transaction.created_at.desc()).limit(10).all()
        )

        # Recent API logs
        recent_logs = ApiLog.query.order_by(ApiLog.created_at.desc()).limit(10).all()
        
        # Transaction trends (last 7 days for charts)
        last_7_days = []
        for i in range(7):
            date = today - timedelta(days=i)
            count = Transaction.query.filter(
                db.func.date(Transaction.created_at) == date
            ).count()
            last_7_days.append({
                'date': date.strftime('%Y-%m-%d'),
                'count': count
            })
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
            
            client_performance.append({
                'client': client,
                'total_transactions': total_transactions,
                'last_30d_transactions': last_30d_transactions,
                'last_7d_transactions': last_7d_transactions,
                'success_rate': round(success_rate, 1),
                'revenue_30d': revenue_30d,
                'last_transaction': last_transaction.created_at if last_transaction else None,
                'is_active_recently': last_transaction.created_at >= (datetime.now() - timedelta(days=7)) if last_transaction else False
            })
        
        return render_template("admin/clients.html", 
                             clients=clients, 
                             client_performance=client_performance)
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
            db.func.date(Transaction.created_at) >= last_30_days
        ).count()
        last_7d_transactions = Transaction.query.filter(
            Transaction.client_id == client_id,
            db.func.date(Transaction.created_at) >= last_7_days
        ).count()
        
        # Success rates
        successful_30d = Transaction.query.filter(
            Transaction.client_id == client_id,
            db.func.date(Transaction.created_at) >= last_30_days,
            Transaction.status == 'completed'
        ).count()
        
        success_rate_30d = (successful_30d / last_30d_transactions * 100) if last_30d_transactions > 0 else 0
        
        # Revenue metrics
        revenue_30d = db.session.query(db.func.sum(Transaction.amount)).filter(
            Transaction.client_id == client_id,
            db.func.date(Transaction.created_at) >= last_30_days,
            Transaction.status == 'completed'
        ).scalar() or 0
        
        revenue_7d = db.session.query(db.func.sum(Transaction.amount)).filter(
            Transaction.client_id == client_id,
            db.func.date(Transaction.created_at) >= last_7_days,
            Transaction.status == 'completed'
        ).scalar() or 0
        
        # Transaction trends (last 30 days)
        daily_transactions = []
        for i in range(30):
            date = today - timedelta(days=i)
            count = Transaction.query.filter(
                Transaction.client_id == client_id,
                db.func.date(Transaction.created_at) == date
            ).count()
            daily_transactions.append({
                'date': date.strftime('%Y-%m-%d'),
                'count': count
            })
        daily_transactions.reverse()
        
        # Service usage breakdown
        service_usage = db.session.query(
            Service.name,
            Service.display_name,
            db.func.count(Transaction.id).label('count'),
            db.func.sum(Transaction.amount).label('revenue')
        ).join(Transaction, Service.id == Transaction.service_id).filter(
            Transaction.client_id == client_id,
            db.func.date(Transaction.created_at) >= last_30_days
        ).group_by(Service.id, Service.name, Service.display_name).all()
        
        # Recent transactions
        recent_transactions = Transaction.query.filter_by(
            client_id=client_id
        ).order_by(Transaction.created_at.desc()).limit(10).all()
        
        # Status breakdown
        status_breakdown = db.session.query(
            Transaction.status,
            db.func.count(Transaction.id).label('count')
        ).filter(
            Transaction.client_id == client_id,
            db.func.date(Transaction.created_at) >= last_30_days
        ).group_by(Transaction.status).all()
        
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
            status_breakdown=status_breakdown
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
                query = query.join(Client).filter(Client.company_name.ilike(f"%{search}%"))
            elif search_type == "mobile_number":
                query = query.filter(Transaction.mobile_number.ilike(f"%{search}%"))
            else:  # search all
                query = query.filter(
                    db.or_(
                        Transaction.unique_id.ilike(f"%{search}%"),
                        Transaction.mobile_number.ilike(f"%{search}%"),
                        Client.company_name.ilike(f"%{search}%")
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
        transactions = query.paginate(
            page=page, 
            per_page=per_page, 
            error_out=False
        )
        
        # Get filter options for dropdowns
        clients = Client.query.filter_by(is_active=True).order_by(Client.company_name).all()
        services = Service.query.order_by(Service.display_name).all()
        
        # Get unique statuses
        statuses = db.session.query(Transaction.status).distinct().all()
        status_options = [status[0] for status in statuses if status[0]]
        
        # Handle CSV export
        if request.args.get('export') == 'csv':
            import csv
            import io
            from flask import make_response
            
            output = io.StringIO()
            writer = csv.writer(output)
            
            # Write header
            writer.writerow([
                'Unique ID', 'Client', 'Service', 'Status', 'Amount', 
                'Mobile Number', 'Created At', 'Updated At'
            ])
            
            # Write data
            for transaction in transactions.items:
                writer.writerow([
                    transaction.unique_id,
                    transaction.client.company_name,
                    transaction.service.display_name,
                    transaction.status,
                    transaction.amount or '',
                    transaction.mobile_number or '',
                    transaction.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                    transaction.updated_at.strftime('%Y-%m-%d %H:%M:%S') if transaction.updated_at else ''
                ])
            
            output.seek(0)
            response = make_response(output.getvalue())
            response.headers['Content-Type'] = 'text/csv'
            response.headers['Content-Disposition'] = f'attachment; filename=transactions_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
            return response

        return render_template(
            "admin/transactions.html", 
            transactions=transactions,
            clients=clients,
            services=services,
            status_options=status_options,
            # Pass current filter values to maintain state
            current_filters={
                'start_date': start_date,
                'end_date': end_date,
                'client_id': client_id,
                'service_id': service_id,
                'status': status,
                'amount_min': amount_min,
                'amount_max': amount_max,
                'search': search,
                'search_type': search_type,
                'sort_by': sort_by,
                'sort_order': sort_order,
                'per_page': per_page
            }
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
        if request.args.get('export') == 'csv':
            import csv
            import io
            from flask import make_response
            
            # Get all transactions for export (no pagination)
            all_transactions = query.all()
            
            output = io.StringIO()
            writer = csv.writer(output)
            
            # Write header
            writer.writerow([
                'Transaction ID', 'Service', 'Status', 'Amount', 
                'Mobile Number', 'Created At', 'Updated At'
            ])
            
            # Write data
            for transaction in all_transactions:
                writer.writerow([
                    transaction.unique_id,
                    transaction.service.display_name,
                    transaction.status,
                    transaction.amount or '',
                    transaction.mobile_number or '',
                    transaction.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                    transaction.updated_at.strftime('%Y-%m-%d %H:%M:%S') if transaction.updated_at else ''
                ])
            
            output.seek(0)
            response = make_response(output.getvalue())
            response.headers['Content-Type'] = 'text/csv'
            response.headers['Content-Disposition'] = f'attachment; filename=client_{client_id}_transactions_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
            return response
        
        # Paginate results
        transactions = query.paginate(
            page=page, 
            per_page=per_page, 
            error_out=False
        )
        
        # Return JSON response
        return jsonify({
            'transactions': [{
                'id': t.id,
                'unique_id': t.unique_id,
                'service_name': t.service.display_name,
                'status': t.status,
                'amount': float(t.amount) if t.amount else None,
                'mobile_number': t.mobile_number,
                'created_at': t.created_at.isoformat(),
                'updated_at': t.updated_at.isoformat() if t.updated_at else None
            } for t in transactions.items],
            'pagination': {
                'page': transactions.page,
                'pages': transactions.pages,
                'per_page': transactions.per_page,
                'total': transactions.total,
                'has_prev': transactions.has_prev,
                'has_next': transactions.has_next,
                'prev_num': transactions.prev_num,
                'next_num': transactions.next_num
            }
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
