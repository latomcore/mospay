-- Example PostgreSQL function for payment status checking
-- This function will be called by the /api/v1/payment/status endpoint
-- Function naming convention: {app_id}_{service_name}_{route}Status

-- Example for app_id: U8EQDpo2, service: mtnmomorwa, route: collection
-- Function name: U8EQDpo2_mtnmomorwa_collectionStatus

CREATE OR REPLACE FUNCTION public.U8EQDpo2_mtnmomorwa_collectionStatus(
    unique_id text, 
    data_input json
) 
RETURNS TABLE(results json) 
LANGUAGE plpgsql AS $function$
DECLARE 
    _status VARCHAR(50):='200';
    _type VARCHAR(50):='object';
    _message TEXT:='Transaction status retrieved successfully';
    _version VARCHAR(50):='1.0.0';
    _action VARCHAR(50):='OUTPUT';
    _command VARCHAR(50):='collectionStatus';
    _servicename VARCHAR(50) :='mtnmomorwa';
    _appId VARCHAR(50) :='U8EQDpo2';
    _appName VARCHAR(50) :='Default Client';
    _entityName VARCHAR(50) :='Default Entity';
    _country VARCHAR(50) :='Default Country';
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
    WHERE t.unique_id = unique_id;
    
    -- If transaction not found, return error
    IF _transaction_data IS NULL THEN
        _status := '404';
        _message := 'Transaction not found';
        _action := 'ERROR';
    END IF;
    
    -- Build the response
    results := (
        SELECT jsonb_pretty(
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
        )
    );
    
    RETURN NEXT;
END;
$function$;

-- Usage example:
-- SELECT * FROM U8EQDpo2_mtnmomorwa_collectionStatus('txn_20250903_001', '{"f000":"mtnmomorwa","f001":"BASE","f002":"collectionStatus","f003":"U8EQDpo2","f004":5000,"f005":"+250788123456","f006":"john_doe","f007":"encrypted_pwd_123","f008":"mypassword","f009":"mobile_app_v1","f010":"txn_20250903_001"}');
