import requests
import json
import uuid
from datetime import datetime
from models import db, Transaction, ApiLog
from sqlalchemy import text
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PaymentProcessor:
    def __init__(self, db_session):
        self.db_session = db_session

    def process_payment_request(self, client, service, payload):
        """Process payment request and call appropriate microservice"""
        try:
            # Generate unique transaction ID
            unique_id = str(uuid.uuid4())

            # Create transaction record
            transaction = Transaction(
                unique_id=unique_id,
                client_id=client.id,
                service_id=service.id,
                status="pending",
                amount=payload.get("f004"),
                mobile_number=payload.get("f005"),
                device_id=payload.get("f009"),
                request_payload=payload,
            )

            self.db_session.add(transaction)
            self.db_session.commit()

            # Call the appropriate PostgreSQL function
            function_name = (
                f"{client.app_id}_{service.name}_{payload.get('f002', 'default')}"
            )
            result = self.call_pg_function(function_name, unique_id, payload)

            if result and result.get("action") == "SERVICE":
                # Call the microservice
                microservice_response = self.call_microservice(
                    result.get("serviceurl"), result.get("servicepayload")
                )

                # Process the response
                response_function_name = f"RESPONSE_{client.app_id}_{service.name}_{payload.get('f002', 'default')}"
                final_result = self.call_pg_response_function(
                    response_function_name,
                    unique_id,
                    payload,
                    200,
                    microservice_response,
                )

                # Update transaction
                transaction.status = "completed"
                transaction.response_payload = final_result
                self.db_session.commit()

                return final_result
            else:
                # Update transaction
                transaction.status = "completed"
                transaction.response_payload = result
                self.db_session.commit()

                return result

        except Exception as e:
            logger.error(f"Error processing payment: {str(e)}")

            # Update transaction status
            if "transaction" in locals():
                transaction.status = "failed"
                transaction.response_payload = {"error": str(e)}
                self.db_session.commit()

            return {
                "status": "500",
                "type": "string",
                "message": f"Payment processing error: {str(e)}",
                "version": "1.0.0",
                "action": "OUTPUT",
                "command": payload.get("f002", "unknown"),
            }

    def call_pg_function(self, function_name, unique_id, data_input):
        """Call PostgreSQL function for payment processing"""
        try:
            # Check if function exists
            check_function = text(
                """
                SELECT routine_name 
                FROM information_schema.routines 
                WHERE routine_name = :function_name 
                AND routine_type = 'FUNCTION'
            """
            )

            result = self.db_session.execute(
                check_function, {"function_name": function_name}
            )
            if not result.fetchone():
                # Function doesn't exist, create a default one
                self.create_default_function(function_name)

            # Call the function
            call_function = text(
                f'SELECT * FROM "{function_name}"(:unique_id, :data_input)'
            )

            result = self.db_session.execute(
                call_function,
                {"unique_id": unique_id, "data_input": json.dumps(data_input)},
            )

            # Get the results
            row = result.fetchone()
            if row and hasattr(row, "results"):
                # row.results is already a Python dict, no need to parse JSON
                return row.results
            else:
                return None

        except Exception as e:
            logger.error(f"Error calling PG function {function_name}: {str(e)}")
            import traceback

            logger.error(f"Full traceback: {traceback.format_exc()}")
            return None

    def call_pg_response_function(
        self, function_name, unique_id, data_input, code, data_output
    ):
        """Call PostgreSQL response function after microservice call"""
        try:
            # Check if function exists
            check_function = text(
                """
                SELECT routine_name 
                FROM information_schema.routines 
                WHERE routine_name = :function_name 
                AND routine_type = 'FUNCTION'
            """
            )

            result = self.db_session.execute(
                check_function, {"function_name": function_name}
            )
            if not result.fetchone():
                # Function doesn't exist, create a default response function
                self.create_default_response_function(function_name)

            # Call the function
            call_function = text(
                f"SELECT * FROM {function_name}(:unique_id, :data_input, :code, :data_output)"
            )
            result = self.db_session.execute(
                call_function,
                {
                    "unique_id": unique_id,
                    "data_input": json.dumps(data_input),
                    "code": code,
                    "data_output": json.dumps(data_output),
                },
            )

            # Get the results
            row = result.fetchone()
            if row and hasattr(row, "results"):
                return json.loads(row.results)
            else:
                return None

        except Exception as e:
            logger.error(
                f"Error calling PG response function {function_name}: {str(e)}"
            )
            return None

    def call_microservice(self, service_url, service_payload):
        """Call external microservice"""
        try:
            headers = {"Content-Type": "application/json", "Accept": "application/json"}

            response = requests.post(
                service_url, json=service_payload, headers=headers, timeout=30
            )

            return {
                "status_code": response.status_code,
                "data": (
                    response.json()
                    if response.headers.get("content-type", "").startswith(
                        "application/json"
                    )
                    else response.text
                ),
            }

        except requests.exceptions.RequestException as e:
            logger.error(f"Error calling microservice {service_url}: {str(e)}")
            return {
                "status_code": 500,
                "data": {"error": f"Microservice call failed: {str(e)}"},
            }

    def create_default_function(self, function_name):
        """Create a default PostgreSQL function if it doesn't exist"""
        try:
            # Extract app_id, microservice_name, and microservice_route from function name
            parts = function_name.split("_")
            if len(parts) >= 3:
                app_id = parts[0]
                microservice_name = parts[1]
                microservice_route = parts[2]
            else:
                app_id = parts[0]
                microservice_name = "default"
                microservice_route = "default"

            # Check if this is a status check function (ends with "Status")
            if microservice_route.endswith("Status"):
                # Create a status check function that queries the database
                create_function_sql = f"""
                CREATE OR REPLACE FUNCTION public."{function_name}"(unique_id text, data_input json)
                RETURNS TABLE(results json)
                LANGUAGE plpgsql
                AS $function$
                DECLARE  
                    _status VARCHAR(50):='200';
                    _type VARCHAR(50):='object';
                    _message TEXT:='Transaction status retrieved'; 
                    _version VARCHAR(50):='1.0.0';
                    _action VARCHAR(50):='OUTPUT';
                    _command VARCHAR(50):='{microservice_route}';
                    _servicename VARCHAR(50) :='{microservice_name}';
                    _appId VARCHAR(50) :='{app_id}';
                    _appName VARCHAR(50):='Default Client';
                    _entityName VARCHAR(50):='Default Entity';
                    _country VARCHAR(50):='Default Country';
                    _transaction_data json;
                    
                BEGIN
                    -- Query the transaction from the database
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
                    ) INTO _transaction_data
                    FROM transactions t
                    WHERE t.unique_id = $1;
                    
                    -- If transaction not found, return error
                    IF _transaction_data IS NULL THEN
                        _status := '404';
                        _message := 'Transaction not found';
                        _action := 'ERROR';
                    END IF;
                    
                    results:=(SELECT 
                        jsonb_pretty(
                            json_build_object(
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
                            )::jsonb
                        ));
                    RETURN NEXT;
                END;
                $function$;
                """
            else:
                # Create a regular microservice function
                create_function_sql = f"""
                CREATE OR REPLACE FUNCTION public."{function_name}"(unique_id text, data_input json)
                RETURNS TABLE(results json)
                LANGUAGE plpgsql
                AS $function$
                DECLARE  
                    _status VARCHAR(50):='200';
                    _type VARCHAR(50):='object';
                    _message TEXT:='Service call initiated'; 
                    _version VARCHAR(50):='1.0.0';
                    _action VARCHAR(50):='SERVICE';
                    _command VARCHAR(50):='{microservice_route}';
                    _servicename VARCHAR(50) :='{microservice_name}';
                    _appId VARCHAR(50) :='{app_id}';
                    _appName VARCHAR(50):='Default Client';
                    _entityName VARCHAR(50):='Default Entity';
                    _country VARCHAR(50):='Default Country';
                    
                BEGIN
                    results:=(SELECT 
                        jsonb_pretty(
                            json_build_object(
                                'status', _status,
                                'type', _type,
                                'message', _message,
                                'version', _version,
                                'action', _action,
                                'command', _command,
                                'appName', _appName,
                                'serviceurl', 'http://{microservice_name}:8080/provider/api/{microservice_route}',
                                'servicepayload', json_build_array(
                                    json_build_object('i', 0, 'v', _appId),
                                    json_build_object('i', 1, 'v', _appName),
                                    json_build_object('i', 2, 'v', _entityName),
                                    json_build_object('i', 3, 'v', _servicename),
                                    json_build_object('i', 4, 'v', _country)
                                )
                            )::jsonb
                        ));
                    RETURN NEXT;
                END;
                $function$;
                """

            self.db_session.execute(text(create_function_sql))
            self.db_session.commit()
            logger.info(f"Created default function: {function_name}")

        except Exception as e:
            logger.error(f"Error creating default function {function_name}: {str(e)}")
            self.db_session.rollback()

    def create_default_response_function(self, function_name):
        """Create a default PostgreSQL response function if it doesn't exist"""
        try:
            # Extract app_id, microservice_name, and microservice_route from function name
            parts = function_name.replace("RESPONSE_", "").split("_")
            if len(parts) >= 3:
                app_id = parts[0]
                microservice_name = parts[1]
                microservice_route = parts[2]
            else:
                app_id = parts[0]
                microservice_name = "default"
                microservice_route = "default"

            create_function_sql = f"""
            CREATE OR REPLACE FUNCTION public.{function_name}(unique_id text, data_input json, integer code, data_output json)
            RETURNS TABLE(results json)
            LANGUAGE plpgsql
            AS $function$
            DECLARE  
                _status VARCHAR(50):='200';
                _type VARCHAR(50):='object';
                _message TEXT:='Request processed successfully'; 
                _version VARCHAR(50):='1.0.0';
                _action VARCHAR(50):='OUTPUT';
                _command VARCHAR(50):='{microservice_route}';
                _servicename VARCHAR(50):='{microservice_name}';
                _appId VARCHAR(50):='{app_id}';
                _appName VARCHAR(50):='Default Client';
                _entityName VARCHAR(50):='Default Entity';
                _country VARCHAR(50):='Default Country';
                
            BEGIN
                results:=(SELECT 
                    jsonb_pretty(
                        json_build_object(
                            'status', _status,
                            'type', _type,
                            'message', _message,
                            'version', _version,
                            'action', _action,
                            'command', _command,
                            'appName', _appName,
                            'serviceurl', 'http://{microservice_name}:8080/provider/api/{microservice_route}',
                            'servicepayload', json_build_array(
                                json_build_object('i', 0, 'v', _appId),
                                json_build_object('i', 1, 'v', _appName),
                                json_build_object('i', 2, 'v', _entityName),
                                json_build_object('i', 3, 'v', _servicename),
                                json_build_object('i', 4, 'v', _country)
                            )
                        )::jsonb
                    ));
                RETURN NEXT;
            END;
            $function$;
            """

            self.db_session.execute(text(create_function_sql))
            self.db_session.commit()
            logger.info(f"Created default response function: {function_name}")

        except Exception as e:
            logger.error(
                f"Error creating default response function {function_name}: {str(e)}"
            )
            self.db_session.rollback()
