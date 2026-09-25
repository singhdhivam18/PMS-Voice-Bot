USE [car-voice-db];
GO

IF OBJECT_ID('dbo.VoiceCallJobs', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.VoiceCallJobs
    (
        job_id INT IDENTITY(1,1) PRIMARY KEY,

        service_id INT NOT NULL,

        idempotency_key VARCHAR(200) NOT NULL,

        correlation_id UNIQUEIDENTIFIER NOT NULL,

        job_status VARCHAR(30) NOT NULL
            CONSTRAINT DF_VoiceCallJobs_JobStatus
            DEFAULT 'PENDING',

        call_status VARCHAR(30) NOT NULL
            CONSTRAINT DF_VoiceCallJobs_CallStatus
            DEFAULT 'NOT_STARTED',

        provider_call_id VARCHAR(200) NULL,

        attempt_count INT NOT NULL
            CONSTRAINT DF_VoiceCallJobs_AttemptCount
            DEFAULT 0,

        last_error NVARCHAR(1000) NULL,

        callback_received BIT NOT NULL
            CONSTRAINT DF_VoiceCallJobs_CallbackReceived
            DEFAULT 0,

        callback_payload NVARCHAR(MAX) NULL,

        created_at DATETIME2 NOT NULL
            CONSTRAINT DF_VoiceCallJobs_CreatedAt
            DEFAULT SYSUTCDATETIME(),

        updated_at DATETIME2 NOT NULL
            CONSTRAINT DF_VoiceCallJobs_UpdatedAt
            DEFAULT SYSUTCDATETIME(),

        consumed_at DATETIME2 NULL,

        call_requested_at DATETIME2 NULL,

        completed_at DATETIME2 NULL,

        CONSTRAINT UQ_VoiceCallJobs_Idempotency
            UNIQUE (idempotency_key),

        CONSTRAINT UQ_VoiceCallJobs_Correlation
            UNIQUE (correlation_id)
    );
END;
GO