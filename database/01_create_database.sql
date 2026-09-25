-- PostgreSQL database creation
-- Source: Dev_voice_db2.sql (PostgreSQL custom-format dump)
-- Run this while connected to a maintenance database such as postgres.

SELECT 'CREATE DATABASE "dev-voice-db"'
WHERE NOT EXISTS (
    SELECT FROM pg_database WHERE datname = 'dev-voice-db'
)\gexec

COMMENT ON DATABASE "dev-voice-db" IS 'PMS voice bot';
