from flask import Blueprint, request, jsonify, current_app
from models import db, Client, Service, Transaction, ApiLog, ClientService
from auth import (
    client_auth_required,
    client_jwt_auth_required,
    admin_required,
    super_admin_required,
)
from flask_jwt_extended import jwt_required, get_jwt_identity
from payment_processor import PaymentProcessor
import json
from datetime import datetime

api = Blueprint("api", __name__)


@api.route("/auth/token", methods=["POST"])
@client_auth_required
def get_token():
    """Get JWT token for authenticated client"""
    try:
        from auth import create_client_token

        # Get client's active services
        client_services = ClientService.query.filter_by(
            client_id=request.client.id, is_active=True
        ).all()

        token = create_client_token(request.client.id, client_services)

        # Log the API call
        api_log = ApiLog(
            client_id=request.client.id,
            endpoint="/api/auth/token",
            method="POST",
            request_data=request.get_json(),
            response_data={"token": token},
            status_code=200,
            ip_address=request.remote_addr,
            user_agent=request.headers.get("User-Agent"),
        )
        db.session.add(api_log)
        db.session.commit()

        return jsonify(
            {
                "status": "200",
                "message": "Token generated successfully",
                "token": token,
                "expires_in": 86400,  # 24 hours
            }
        )

    except Exception as e:
        return (
            jsonify({"status": "500", "message": f"Error generating token: {str(e)}"}),
            500,
        )


@api.route("/payment/process", methods=["POST"])
@jwt_required()
def process_payment():
    """Process payment request"""
    try:
        data = request.get_json()

        # Validate required fields
        required_fields = [
            "f000",
            "f001",
            "f002",
            "f003",
            "f004",
            "f005",
            "f006",
            "f007",
            "f008",
            "f009",
            "f010",
        ]
        missing_fields = [field for field in required_fields if field not in data]

        if missing_fields:
            return (
                jsonify(
                    {
                        "status": "400",
                        "message": f'Missing required fields: {", ".join(missing_fields)}',
                    }
                ),
                400,
            )

        # Get client from JWT token additional claims
        from flask_jwt_extended import get_jwt

        jwt_data = get_jwt()
        if not jwt_data or jwt_data.get("type") != "client":
            return jsonify({"status": "400", "message": "Invalid token type"}), 400

        client = Client.query.get(jwt_data["client_id"])
        if not client or not client.is_active:
            return (
                jsonify({"status": "400", "message": "Invalid or inactive client"}),
                400,
            )

        # Validate app_id matches
        if data["f003"] != client.app_id:
            return jsonify({"status": "400", "message": "App ID mismatch"}), 400

        # Find the service
        service = Service.query.filter_by(name=data["f000"], is_active=True).first()
        if not service:
            return (
                jsonify(
                    {
                        "status": "400",
                        "message": f'Service {data["f000"]} not found or inactive',
                    }
                ),
                400,
            )

        # Check if client has access to this service
        from models import ClientService

        client_service = ClientService.query.filter_by(
            client_id=client.id, service_id=service.id, is_active=True
        ).first()

        if not client_service:
            return (
                jsonify(
                    {
                        "status": "403",
                        "message": f'Access denied to service {data["f001"]}',
                    }
                ),
                403,
            )

        # Process the payment
        processor = PaymentProcessor(db.session)
        result = processor.process_payment_request(client, service, data)

        # Log the API call
        api_log = ApiLog(
            client_id=client.id,
            endpoint="/api/payment/process",
            method="POST",
            request_data=data,
            response_data=result,
            status_code=200,
            ip_address=request.remote_addr,
            user_agent=request.headers.get("User-Agent"),
        )
        db.session.add(api_log)
        db.session.commit()

        return jsonify(result)

    except Exception as e:
        return (
            jsonify(
                {"status": "500", "message": f"Payment processing error: {str(e)}"}
            ),
            500,
        )


@api.route("/payment/status", methods=["POST"])
@jwt_required()
def get_payment_status():
    """Get payment transaction status using PostgreSQL function"""
    try:
        data = request.get_json()

        # Validate required fields (same as payment/process)
        required_fields = [
            "f000",
            "f001",
            "f002",
            "f003",
            "f004",
            "f005",
            "f006",
            "f007",
            "f008",
            "f009",
            "f010",
        ]
        missing_fields = [field for field in required_fields if field not in data]

        if missing_fields:
            return (
                jsonify(
                    {
                        "status": "400",
                        "message": f'Missing required fields: {", ".join(missing_fields)}',
                    }
                ),
                400,
            )

        # Get client from JWT token additional claims
        from flask_jwt_extended import get_jwt

        jwt_data = get_jwt()
        if not jwt_data or jwt_data.get("type") != "client":
            return jsonify({"status": "400", "message": "Invalid token type"}), 400

        client = Client.query.get(jwt_data["client_id"])
        if not client or not client.is_active:
            return (
                jsonify({"status": "400", "message": "Invalid or inactive client"}),
                400,
            )

        # Validate app_id matches
        if data["f003"] != client.app_id:
            return jsonify({"status": "400", "message": "App ID mismatch"}), 400

        # Find the service
        service = Service.query.filter_by(name=data["f000"], is_active=True).first()
        if not service:
            return (
                jsonify(
                    {
                        "status": "400",
                        "message": f'Service {data["f000"]} not found or inactive',
                    }
                ),
                400,
            )

        # Check if client has access to this service
        from models import ClientService

        client_service = ClientService.query.filter_by(
            client_id=client.id, service_id=service.id, is_active=True
        ).first()

        if not client_service:
            return (
                jsonify(
                    {
                        "status": "403",
                        "message": f'Access denied to service {data["f000"]}',
                    }
                ),
                403,
            )

        # Modify the payload for database query
        status_payload = data.copy()
        # f000 remains the same (original service name)
        status_payload["f001"] = "BASE"  # Indicates database query
        status_payload["f002"] = (
            f"{data['f002']}Status"  # Append "Status" to the route name
        )

        # Get unique_id from payload (f010 field)
        unique_id = data["f010"]

        # Process the status check using the same PaymentProcessor logic
        processor = PaymentProcessor(db.session)

        # Call the appropriate PostgreSQL function with routeStatus
        function_name = f"{client.app_id}_{service.name}_{data['f002']}Status"
        result = processor.call_pg_function(function_name, unique_id, status_payload)

        if not result:
            return (
                jsonify(
                    {
                        "status": "500",
                        "message": "Error calling status check function",
                    }
                ),
                500,
            )

        # Log the API call
        api_log = ApiLog(
            client_id=client.id,
            endpoint="/api/payment/status",
            method="POST",
            request_data=data,
            response_data=result,
            status_code=200,
            ip_address=request.remote_addr,
            user_agent=request.headers.get("User-Agent"),
        )
        db.session.add(api_log)
        db.session.commit()

        return jsonify(result)

    except Exception as e:
        return (
            jsonify(
                {
                    "status": "500",
                    "message": f"Error retrieving transaction status: {str(e)}",
                }
            ),
            500,
        )


@api.route("/client/services", methods=["GET"])
@client_auth_required
def get_client_services():
    """Get services available to the authenticated client"""
    try:
        from models import ClientService

        client_services = (
            ClientService.query.filter_by(client_id=request.client.id, is_active=True)
            .join(Service)
            .all()
        )

        services = []
        for cs in client_services:
            service = cs.service
            services.append(
                {
                    "service_id": service.id,
                    "service_name": service.name,
                    "display_name": service.display_name,
                    "description": service.description,
                    "service_url": service.service_url,
                }
            )

        return jsonify(
            {
                "status": "200",
                "message": "Services retrieved successfully",
                "services": services,
            }
        )

    except Exception as e:
        return (
            jsonify(
                {"status": "500", "message": f"Error retrieving services: {str(e)}"}
            ),
            500,
        )


@api.route("/client/profile", methods=["GET"])
@client_auth_required
def get_client_profile():
    """Get client profile information"""
    try:
        client = request.client
        return jsonify(
            {
                "status": "200",
                "message": "Profile retrieved successfully",
                "profile": {
                    "app_id": client.app_id,
                    "company_name": client.company_name,
                    "contact_person": client.contact_person,
                    "email": client.email,
                    "phone": client.phone,
                    "address": client.address,
                    "api_username": client.api_username,
                    "is_active": client.is_active,
                    "created_at": client.created_at.isoformat(),
                },
            }
        )

    except Exception as e:
        return (
            jsonify(
                {"status": "500", "message": f"Error retrieving profile: {str(e)}"}
            ),
            500,
        )


@api.route("/transactions", methods=["GET"])
@client_auth_required
def get_transactions():
    """Get client's transaction history"""
    try:
        page = request.args.get("page", 1, type=int)
        per_page = request.args.get("per_page", 20, type=int)

        transactions = (
            Transaction.query.filter_by(client_id=request.client.id)
            .order_by(Transaction.created_at.desc())
            .paginate(page=page, per_page=per_page, error_out=False)
        )

        transaction_list = []
        for transaction in transactions.items:
            transaction_list.append(
                {
                    "unique_id": transaction.unique_id,
                    "service_name": transaction.service.name,
                    "status": transaction.status,
                    "amount": str(transaction.amount) if transaction.amount else None,
                    "mobile_number": transaction.mobile_number,
                    "created_at": transaction.created_at.isoformat(),
                    "updated_at": transaction.updated_at.isoformat(),
                }
            )

        return jsonify(
            {
                "status": "200",
                "message": "Transactions retrieved successfully",
                "transactions": transaction_list,
                "pagination": {
                    "page": page,
                    "per_page": per_page,
                    "total": transactions.total,
                    "pages": transactions.pages,
                },
            }
        )

    except Exception as e:
        return (
            jsonify(
                {"status": "500", "message": f"Error retrieving transactions: {str(e)}"}
            ),
            500,
        )


@api.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint"""
    return jsonify(
        {
            "status": "200",
            "message": "MosPay is running",
            "timestamp": datetime.utcnow().isoformat(),
        }
    )
