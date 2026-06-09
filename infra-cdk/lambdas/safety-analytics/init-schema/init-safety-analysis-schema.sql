-- Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
-- SPDX-License-Identifier: Apache-2.0

--
-- Aurora PostgreSQL Schema Initialization
--
-- This script creates tables in Aurora PostgreSQL that mirror DynamoDB tables
-- for safety_analysis and reporting purposes. Data is replicated from DynamoDB via Lambda.
--
-- Run this script after deploying the CDK stack:
-- psql -h <aurora-endpoint> -U <username> -d safety_analysis -f init-safety-analysis-schema.sql
--

-- ======================================================================
-- Feedback Table
-- Stores user feedback on agent responses
-- ======================================================================

CREATE TABLE IF NOT EXISTS public."Feedback" (
    "feedback_id" VARCHAR(100) PRIMARY KEY,
    "session_id" VARCHAR(100) NOT NULL,
    "message" TEXT NOT NULL,
    "feedback_type" VARCHAR(20) NOT NULL CHECK ("feedback_type" IN ('positive', 'negative')),
    "comment" TEXT,
    "timestamp" BIGINT NOT NULL,
    "created_at" TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index for querying by feedback type and timestamp
CREATE INDEX IF NOT EXISTS idx_feedback_type_timestamp
    ON public."Feedback" ("feedback_type", "timestamp" DESC);

-- Index for querying by session
CREATE INDEX IF NOT EXISTS idx_feedback_session
    ON public."Feedback" ("session_id");

COMMENT ON TABLE public."Feedback" IS 'User feedback on agent responses replicated from DynamoDB';
COMMENT ON COLUMN public."Feedback"."feedback_id" IS 'Unique identifier for feedback';
COMMENT ON COLUMN public."Feedback"."session_id" IS 'Conversation session identifier';
COMMENT ON COLUMN public."Feedback"."feedback_type" IS 'positive or negative';
COMMENT ON COLUMN public."Feedback"."timestamp" IS 'Unix timestamp (milliseconds)';

-- ======================================================================
-- Safety Events Table
-- Stores hospital safety events for monitoring and analysis
-- ======================================================================

CREATE TABLE IF NOT EXISTS public."SafetyEvents" (
    "event_id" VARCHAR(100) NOT NULL,
    "timestamp" VARCHAR(50) NOT NULL,
    "event_type" VARCHAR(50) NOT NULL,
    "location" VARCHAR(100),
    "severity" VARCHAR(20),
    "description" TEXT,
    "patient_id" VARCHAR(100),
    "created_at" TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY ("event_id", "timestamp")
);

-- Index for querying by event type
CREATE INDEX IF NOT EXISTS idx_safety_events_type
    ON public."SafetyEvents" ("event_type", "timestamp" DESC);

-- Index for querying by location (for infection pattern analysis)
CREATE INDEX IF NOT EXISTS idx_safety_events_location
    ON public."SafetyEvents" ("location", "timestamp" DESC);

-- Index for severity analysis
CREATE INDEX IF NOT EXISTS idx_safety_events_severity
    ON public."SafetyEvents" ("severity", "timestamp" DESC);

COMMENT ON TABLE public."SafetyEvents" IS 'Hospital safety events replicated from DynamoDB';
COMMENT ON COLUMN public."SafetyEvents"."event_type" IS 'Type of safety event (fall, infection, medication_error)';
COMMENT ON COLUMN public."SafetyEvents"."severity" IS 'Event severity (low, medium, high, critical)';

-- ======================================================================
-- Safety Analysis Table
-- Stores specialist agent analysis results for safety events
-- ======================================================================

CREATE TABLE IF NOT EXISTS public."SafetyAnalysis" (
    "analysis_id" VARCHAR(100) NOT NULL,
    "timestamp" VARCHAR(50) NOT NULL,
    "event_id" VARCHAR(100) NOT NULL,
    "analyst_type" VARCHAR(50),
    "findings" TEXT,
    "recommendations" TEXT,
    "risk_score" INTEGER,
    "created_at" TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY ("analysis_id", "timestamp")
);

-- Index for querying analysis by event
CREATE INDEX IF NOT EXISTS idx_safety_analysis_event
    ON public."SafetyAnalysis" ("event_id", "timestamp" DESC);

-- Index for querying by analyst type
CREATE INDEX IF NOT EXISTS idx_safety_analysis_analyst
    ON public."SafetyAnalysis" ("analyst_type", "timestamp" DESC);

-- Index for risk analysis
CREATE INDEX IF NOT EXISTS idx_safety_analysis_risk
    ON public."SafetyAnalysis" ("risk_score" DESC, "timestamp" DESC);

COMMENT ON TABLE public."SafetyAnalysis" IS 'Specialist agent analysis results replicated from DynamoDB';
COMMENT ON COLUMN public."SafetyAnalysis"."analyst_type" IS 'Type of specialist agent (falls_prevention, infection_control, medication_safety)';
COMMENT ON COLUMN public."SafetyAnalysis"."risk_score" IS 'Risk assessment score (0-100)';

-- ======================================================================
-- Materialized Views for Analytics
-- ======================================================================

-- Feedback summary by type and time period
CREATE MATERIALIZED VIEW IF NOT EXISTS public."FeedbackSummary" AS
SELECT
    DATE_TRUNC('day', TO_TIMESTAMP("timestamp" / 1000)) AS date,
    "feedback_type",
    COUNT(*) AS feedback_count,
    COUNT(DISTINCT "session_id") AS unique_sessions
FROM public."Feedback"
GROUP BY date, "feedback_type"
ORDER BY date DESC, "feedback_type";

CREATE INDEX IF NOT EXISTS idx_feedback_summary_date
    ON public."FeedbackSummary" (date DESC);

-- Safety events summary by type and severity
CREATE MATERIALIZED VIEW IF NOT EXISTS public."SafetyEventsSummary" AS
SELECT
    DATE_TRUNC('day', TO_TIMESTAMP("timestamp", 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"')) AS date,
    "event_type",
    "severity",
    "location",
    COUNT(*) AS event_count
FROM public."SafetyEvents"
GROUP BY date, "event_type", "severity", "location"
ORDER BY date DESC, event_count DESC;

CREATE INDEX IF NOT EXISTS idx_safety_events_summary_date
    ON public."SafetyEventsSummary" (date DESC);

-- Combined events and analysis view
CREATE MATERIALIZED VIEW IF NOT EXISTS public."SafetyEventsWithAnalysis" AS
SELECT
    e."event_id",
    e."timestamp" AS event_timestamp,
    e."event_type",
    e."location",
    e."severity",
    e."description",
    a."analysis_id",
    a."analyst_type",
    a."findings",
    a."recommendations",
    a."risk_score"
FROM public."SafetyEvents" e
LEFT JOIN public."SafetyAnalysis" a ON e."event_id" = a."event_id"
ORDER BY e."timestamp" DESC;

CREATE INDEX IF NOT EXISTS idx_safety_combined_event_id
    ON public."SafetyEventsWithAnalysis" ("event_id");

-- ======================================================================
-- Refresh materialized views function (call periodically)
-- ======================================================================

CREATE OR REPLACE FUNCTION refresh_all_materialized_views()
RETURNS void AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY public."FeedbackSummary";
    REFRESH MATERIALIZED VIEW CONCURRENTLY public."SafetyEventsSummary";
    REFRESH MATERIALIZED VIEW CONCURRENTLY public."SafetyEventsWithAnalysis";
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION refresh_all_materialized_views() IS 'Refresh all materialized views for safety_analysis (run daily)';

-- ======================================================================
-- Grant permissions
-- ======================================================================

-- Grant Lambda replication role read/write access to tables
-- (Replace 'replication_role' with actual role name after deployment)
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO replication_role;

-- Grant read-only access for safety_analysis users
-- CREATE ROLE safety_analysis_reader;
-- GRANT SELECT ON ALL TABLES IN SCHEMA public TO safety_analysis_reader;
-- GRANT SELECT ON ALL MATERIALIZED VIEWS IN SCHEMA public TO safety_analysis_reader;
