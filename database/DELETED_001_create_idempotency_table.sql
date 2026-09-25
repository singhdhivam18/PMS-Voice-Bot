-- ============================================================================
-- Idempotency tracking table for the Maintenance Call Publisher Worker
-- Run this once against the existing SQL Server database.
-- ============================================================================

IF NOT EXISTS (
    SELECT 1 FROM sys.tables t
    JOIN sys.schemas s ON s.schema_id = t.schema_id
    WHERE t.name = 'MaintenanceCallIdempotency' AND s.name = 'dbo'
)
BEGIN
    CREATE TABLE dbo.MaintenanceCallIdempotency
    (
        idempotency_key       VARCHAR(200)     NOT NULL PRIMARY KEY,
        correlation_id        UNIQUEIDENTIFIER NOT NULL,
        service_id            INT              NOT NULL,
        carno                 VARCHAR(20)      NOT NULL,
        maintenance_type      VARCHAR(50)      NOT NULL,
        due_maintenance_date  DATE             NOT NULL,
        status                VARCHAR(20)      NOT NULL DEFAULT 'PENDING',  -- PENDING | PUBLISHED | FAILED
        attempt_count         INT              NOT NULL DEFAULT 0,
        last_error            VARCHAR(1000)    NULL,
        created_at            DATETIME2        NOT NULL DEFAULT SYSUTCDATETIME(),
        updated_at            DATETIME2        NOT NULL DEFAULT SYSUTCDATETIME()
    );

    CREATE INDEX IX_MaintenanceCallIdempotency_ServiceId
        ON dbo.MaintenanceCallIdempotency (service_id);

    CREATE INDEX IX_MaintenanceCallIdempotency_Status
        ON dbo.MaintenanceCallIdempotency (status);
END
GO
