\getenv catalog_password CATALOG_PASSWORD
\getenv order_password ORDER_PASSWORD
\getenv worker_password WORKER_PASSWORD
BEGIN;
SELECT pg_advisory_xact_lock(710012);
CREATE SCHEMA IF NOT EXISTS :"brand";
SELECT format('CREATE ROLE %I', role_name)
FROM (VALUES (:'catalog'), (:'orders'), (:'worker')) AS roles(role_name)
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = role_name)
\gexec
ALTER ROLE :"catalog" LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD :'catalog_password';
ALTER ROLE :"orders" LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD :'order_password';
ALTER ROLE :"worker" LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD :'worker_password';
REVOKE CONNECT, TEMP ON DATABASE :"DBNAME" FROM PUBLIC;
GRANT CONNECT ON DATABASE :"DBNAME" TO :"catalog", :"orders", :"worker";
REVOKE ALL ON SCHEMA :"brand" FROM PUBLIC;
GRANT USAGE ON SCHEMA :"brand" TO :"catalog", :"orders", :"worker";
SET LOCAL search_path TO :"brand", pg_catalog;
CREATE TABLE IF NOT EXISTS schema_migrations (version integer PRIMARY KEY);
SELECT NOT EXISTS (SELECT FROM schema_migrations WHERE version = 1) AS needs_v1 \gset
\if :needs_v1
\ir V001__tenant_tables.sql
INSERT INTO schema_migrations VALUES (1);
\endif
SELECT NOT EXISTS (SELECT FROM schema_migrations WHERE version = 2) AS needs_v2 \gset
\if :needs_v2
\ir V002__outbox_activation.sql
INSERT INTO schema_migrations VALUES (2);
\endif
GRANT SELECT ON menus TO :"catalog", :"orders";
GRANT SELECT, INSERT ON orders TO :"orders";
GRANT SELECT ON orders TO :"worker";
GRANT SELECT, INSERT ON outbox_events TO :"orders";
GRANT UPDATE (published_at, attempts, next_attempt_at) ON outbox_events TO :"orders";
GRANT SELECT (event_id, order_id) ON outbox_events TO :"worker";
GRANT UPDATE (status) ON orders TO :"worker";
GRANT SELECT, INSERT ON processed_events TO :"worker";
COMMIT;
