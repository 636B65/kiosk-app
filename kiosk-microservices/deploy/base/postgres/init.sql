-- One database per service (database-per-service: no service reads another's tables).
-- Runs once, when the Postgres data directory is first initialised.
CREATE DATABASE auth;
CREATE DATABASE catalog;
CREATE DATABASE customers;
CREATE DATABASE orders;
CREATE DATABASE settings;
CREATE DATABASE audit;
