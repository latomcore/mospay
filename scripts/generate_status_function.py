#!/usr/bin/env python3
"""
Generate a PostgreSQL status-check function for MosPay with proper casing and logs.

Usage:
  python scripts/generate_status_function.py \
    --app-id U8EQDpo2 \
    --service mtnmomorwa \
    --route collection \
    --dsn "postgresql://user:pass@host:5432/dbname"

Notes:
- Creates function: "{app_id}_{service}_{route}Status"
- Action is OUTPUT; function queries transactions by unique_id
- Adds RAISE NOTICE logs for inputs and flow
- Safe to re-run (CREATE OR REPLACE FUNCTION)
"""

import argparse
import sys
import psycopg2
import json


def build_function_sql(app_id: str, service: str, route: str) -> str:
    func_name = f"{app_id}_{service}_{route}Status"
    command = f"{route}Status"
    return f"""
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
    _servicename VARCHAR(50) :='{service}';
    _appId VARCHAR(50) :='{app_id}';
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate status-check PG function")
    parser.add_argument("--app-id", required=True, help="Client app_id, e.g., U8EQDpo2")
    parser.add_argument(
        "--service", required=True, help="Service name, e.g., mtnmomorwa"
    )
    parser.add_argument("--route", required=True, help="Route name, e.g., collection")
    parser.add_argument(
        "--dsn",
        required=True,
        help="Postgres DSN (SQLAlchemy-style accepted by psycopg2)",
    )

    args = parser.parse_args()

    sql = build_function_sql(args.app_id, args.service, args.route)

    try:
        conn = psycopg2.connect(args.dsn)
        cur = conn.cursor()
        cur.execute(sql)
        conn.commit()
        print(f'Created function: "{args.app_id}_{args.service}_{args.route}Status"')
        # Quick smoke test with the provided route format
        payload = {
            "f000": args.service,
            "f001": "BASE",
            "f002": f"{args.route}Status",
            "f003": args.app_id,
            "f004": 0,
            "f005": "",
            "f006": "",
            "f007": "",
            "f008": "",
            "f009": "",
            "f010": "txn_sample_001",
        }
        cur.execute(
            f'SELECT * FROM "{args.app_id}_{args.service}_{args.route}Status"(%s, %s)',
            ("txn_sample_001", json.dumps(payload)),
        )
        _ = cur.fetchone()  # ignore result; just ensure function executability
        cur.close()
        conn.close()
        print("Smoke test executed (function callable).")
        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
