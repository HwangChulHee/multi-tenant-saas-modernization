\getenv pos_password POS_DB_PASSWORD
BEGIN;
SELECT pg_advisory_xact_lock(710012);
SELECT 'CREATE ROLE mock_pos_app' WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'mock_pos_app')
\gexec
ALTER ROLE mock_pos_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD :'pos_password';
GRANT CONNECT ON DATABASE :"DBNAME" TO mock_pos_app;
CREATE SCHEMA IF NOT EXISTS mock_pos;
REVOKE ALL ON SCHEMA mock_pos FROM PUBLIC;
GRANT USAGE ON SCHEMA mock_pos TO mock_pos_app;

CREATE TABLE IF NOT EXISTS mock_pos.deliveries (
    event_id uuid PRIMARY KEY,
    tenant_id text NOT NULL CHECK (tenant_id IN ('brand_a', 'brand_b', 'brand_c')),
    order_id uuid NOT NULL,
    request_id uuid NOT NULL,
    attempts integer NOT NULL,
    accepted_at timestamptz,
    UNIQUE (tenant_id, order_id)
);
GRANT SELECT, INSERT ON mock_pos.deliveries TO mock_pos_app;
GRANT UPDATE (attempts, accepted_at) ON mock_pos.deliveries TO mock_pos_app;
COMMIT;
