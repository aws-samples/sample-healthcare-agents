# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""
One-time Lambda function to initialize Aurora PostgreSQL schema for safety analysis.

This Lambda runs the SQL initialization script to create tables, indexes, and views
for the safety analysis database.
"""

import json
import os
import boto3
import psycopg2
from aws_lambda_powertools import Logger

logger = Logger()
secrets_client = boto3.client('secretsmanager')


def get_db_connection():
    """Get database connection using credentials from Secrets Manager"""
    secret_arn = os.environ['DB_SECRET_ARN']

    # Retrieve secret
    response = secrets_client.get_secret_value(SecretId=secret_arn)
    secret = json.loads(response['SecretString'])

    # Connect to PostgreSQL
    conn = psycopg2.connect(
        user=secret['username'],
        password=secret['password'],
        host=secret['host'],
        dbname=secret['dbname'],
        port=secret['port']
    )

    return conn


@logger.inject_lambda_context(log_event=True)
def handler(event, context):
    """Initialize Aurora schema"""

    try:
        logger.info("Connecting to Aurora PostgreSQL")
        conn = get_db_connection()
        cursor = conn.cursor()

        # Read SQL file
        sql_script = """
-- Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
-- SPDX-License-Identifier: Apache-2.0

-- Safety Analysis Aurora PostgreSQL Schema
-- This schema mirrors DynamoDB tables for analytics and reporting

-- Feedback table
CREATE TABLE IF NOT EXISTS public."Feedback" (
    feedback_id VARCHAR(255) PRIMARY KEY,
    session_id VARCHAR(255),
    message TEXT,
    feedback_type VARCHAR(50),
    comment TEXT,
    timestamp TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_feedback_session ON public."Feedback"(session_id);
CREATE INDEX IF NOT EXISTS idx_feedback_timestamp ON public."Feedback"(timestamp);
CREATE INDEX IF NOT EXISTS idx_feedback_type ON public."Feedback"(feedback_type);

-- Safety Events table
CREATE TABLE IF NOT EXISTS public."SafetyEvents" (
    event_id VARCHAR(255) PRIMARY KEY,
    timestamp TIMESTAMP,
    event_type VARCHAR(100),
    location VARCHAR(255),
    severity VARCHAR(50),
    description TEXT,
    patient_id VARCHAR(255)
);

-- Add new columns if they don't exist (for existing tables)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_schema='public' AND table_name='SafetyEvents' AND column_name='patient_mrn') THEN
        ALTER TABLE public."SafetyEvents" ADD COLUMN patient_mrn VARCHAR(255);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_schema='public' AND table_name='SafetyEvents' AND column_name='clinical_state') THEN
        ALTER TABLE public."SafetyEvents" ADD COLUMN clinical_state TEXT;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_schema='public' AND table_name='SafetyEvents' AND column_name='equipment_involved') THEN
        ALTER TABLE public."SafetyEvents" ADD COLUMN equipment_involved JSONB;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_schema='public' AND table_name='SafetyEvents' AND column_name='harm_level') THEN
        ALTER TABLE public."SafetyEvents" ADD COLUMN harm_level VARCHAR(50);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_schema='public' AND table_name='SafetyEvents' AND column_name='immediate_actions') THEN
        ALTER TABLE public."SafetyEvents" ADD COLUMN immediate_actions JSONB;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_schema='public' AND table_name='SafetyEvents' AND column_name='root_causes') THEN
        ALTER TABLE public."SafetyEvents" ADD COLUMN root_causes JSONB;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_schema='public' AND table_name='SafetyEvents' AND column_name='timeline_details') THEN
        ALTER TABLE public."SafetyEvents" ADD COLUMN timeline_details JSONB;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_schema='public' AND table_name='SafetyEvents' AND column_name='event_date') THEN
        ALTER TABLE public."SafetyEvents" ADD COLUMN event_date VARCHAR(255);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_schema='public' AND table_name='SafetyEvents' AND column_name='date_reported') THEN
        ALTER TABLE public."SafetyEvents" ADD COLUMN date_reported VARCHAR(255);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_schema='public' AND table_name='SafetyEvents' AND column_name='event_classification') THEN
        ALTER TABLE public."SafetyEvents" ADD COLUMN event_classification VARCHAR(50);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_schema='public' AND table_name='SafetyEvents' AND column_name='patient_age_category') THEN
        ALTER TABLE public."SafetyEvents" ADD COLUMN patient_age_category VARCHAR(50);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_schema='public' AND table_name='SafetyEvents' AND column_name='rescue_attempted') THEN
        ALTER TABLE public."SafetyEvents" ADD COLUMN rescue_attempted VARCHAR(20);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_schema='public' AND table_name='SafetyEvents' AND column_name='patient_family_notified') THEN
        ALTER TABLE public."SafetyEvents" ADD COLUMN patient_family_notified VARCHAR(20);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_schema='public' AND table_name='SafetyEvents' AND column_name='increased_length_of_stay') THEN
        ALTER TABLE public."SafetyEvents" ADD COLUMN increased_length_of_stay VARCHAR(20);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_schema='public' AND table_name='SafetyEvents' AND column_name='time_harm_assessed') THEN
        ALTER TABLE public."SafetyEvents" ADD COLUMN time_harm_assessed VARCHAR(50);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_safety_events_timestamp ON public."SafetyEvents"(timestamp);
CREATE INDEX IF NOT EXISTS idx_safety_events_type ON public."SafetyEvents"(event_type);
CREATE INDEX IF NOT EXISTS idx_safety_events_severity ON public."SafetyEvents"(severity);
CREATE INDEX IF NOT EXISTS idx_safety_events_location ON public."SafetyEvents"(location);
CREATE INDEX IF NOT EXISTS idx_safety_events_patient ON public."SafetyEvents"(patient_id);
CREATE INDEX IF NOT EXISTS idx_safety_events_mrn ON public."SafetyEvents"(patient_mrn);
CREATE INDEX IF NOT EXISTS idx_safety_events_harm_level ON public."SafetyEvents"(harm_level);
CREATE INDEX IF NOT EXISTS idx_safety_events_event_date ON public."SafetyEvents"(event_date);
CREATE INDEX IF NOT EXISTS idx_safety_events_date_reported ON public."SafetyEvents"(date_reported);
CREATE INDEX IF NOT EXISTS idx_safety_events_event_classification ON public."SafetyEvents"(event_classification);
CREATE INDEX IF NOT EXISTS idx_safety_events_patient_age_category ON public."SafetyEvents"(patient_age_category);
CREATE INDEX IF NOT EXISTS idx_safety_events_rescue_attempted ON public."SafetyEvents"(rescue_attempted);
CREATE INDEX IF NOT EXISTS idx_safety_events_patient_family_notified ON public."SafetyEvents"(patient_family_notified);

-- GIN indexes for JSONB columns to enable efficient querying
CREATE INDEX IF NOT EXISTS idx_safety_events_equipment_gin ON public."SafetyEvents" USING GIN (equipment_involved);
CREATE INDEX IF NOT EXISTS idx_safety_events_actions_gin ON public."SafetyEvents" USING GIN (immediate_actions);
CREATE INDEX IF NOT EXISTS idx_safety_events_root_causes_gin ON public."SafetyEvents" USING GIN (root_causes);

-- Safety Analysis table
CREATE TABLE IF NOT EXISTS public."SafetyAnalysis" (
    analysis_id VARCHAR(255) PRIMARY KEY,
    timestamp TIMESTAMP,
    event_id VARCHAR(255),
    analyst_type VARCHAR(100),
    findings TEXT,
    recommendations TEXT,
    risk_score INTEGER
);

CREATE INDEX IF NOT EXISTS idx_safety_analysis_timestamp ON public."SafetyAnalysis"(timestamp);
CREATE INDEX IF NOT EXISTS idx_safety_analysis_event ON public."SafetyAnalysis"(event_id);
CREATE INDEX IF NOT EXISTS idx_safety_analysis_type ON public."SafetyAnalysis"(analyst_type);
CREATE INDEX IF NOT EXISTS idx_safety_analysis_risk ON public."SafetyAnalysis"(risk_score);

-- Foreign key relationship
ALTER TABLE public."SafetyAnalysis"
DROP CONSTRAINT IF EXISTS fk_safety_analysis_event;

ALTER TABLE public."SafetyAnalysis"
ADD CONSTRAINT fk_safety_analysis_event
FOREIGN KEY (event_id) REFERENCES public."SafetyEvents"(event_id);

-- Materialized views for analytics

-- Drop and recreate materialized views to pick up new columns
DROP MATERIALIZED VIEW IF EXISTS mv_high_risk_events CASCADE;
DROP MATERIALIZED VIEW IF EXISTS mv_feedback_summary CASCADE;
DROP MATERIALIZED VIEW IF EXISTS mv_safety_events_by_location CASCADE;
DROP MATERIALIZED VIEW IF EXISTS public."FeedbackSummary" CASCADE;
DROP MATERIALIZED VIEW IF EXISTS public."SafetyEventsSummary" CASCADE;
DROP MATERIALIZED VIEW IF EXISTS public."SafetyEventsWithAnalysis" CASCADE;

-- High-risk events summary
CREATE MATERIALIZED VIEW mv_high_risk_events AS
SELECT
    e."event_id",
    e."timestamp",
    e."event_type",
    e."event_classification",
    e."location",
    e."severity",
    e."description",
    e."patient_mrn",
    e."patient_age_category",
    e."harm_level",
    e."equipment_involved",
    e."immediate_actions",
    e."root_causes",
    e."event_date",
    e."date_reported",
    e."rescue_attempted",
    e."patient_family_notified",
    e."increased_length_of_stay",
    e."time_harm_assessed",
    a."risk_score",
    a."findings",
    a."recommendations"
FROM public."SafetyEvents" e
LEFT JOIN public."SafetyAnalysis" a ON e."event_id" = a."event_id"
WHERE a."risk_score" >= 7 OR UPPER(e."severity") IN ('HIGH', 'CRITICAL')
ORDER BY e."timestamp" DESC;

CREATE INDEX IF NOT EXISTS idx_mv_high_risk_timestamp ON mv_high_risk_events("timestamp");

-- Feedback summary by type
CREATE MATERIALIZED VIEW mv_feedback_summary AS
SELECT
    "feedback_type",
    DATE_TRUNC('day', "timestamp") as day,
    COUNT(*) as count,
    COUNT(CASE WHEN "comment" IS NOT NULL AND "comment" != '' THEN 1 END) as with_comments
FROM public."Feedback"
GROUP BY "feedback_type", DATE_TRUNC('day', "timestamp")
ORDER BY day DESC, "feedback_type";

-- Safety events by location and type
CREATE MATERIALIZED VIEW mv_safety_events_by_location AS
SELECT
    "location",
    "event_type",
    "severity",
    COUNT(*) as event_count,
    AVG(a."risk_score") as avg_risk_score
FROM public."SafetyEvents" e
LEFT JOIN public."SafetyAnalysis" a ON e."event_id" = a."event_id"
GROUP BY "location", "event_type", "severity"
ORDER BY event_count DESC;

-- Feedback summary by type and time period
CREATE MATERIALIZED VIEW public."FeedbackSummary" AS
SELECT
    DATE_TRUNC('day', "timestamp") AS date,
    "feedback_type",
    COUNT(*) AS feedback_count,
    COUNT(DISTINCT "session_id") AS unique_sessions
FROM public."Feedback"
GROUP BY date, "feedback_type"
ORDER BY date DESC, "feedback_type";

CREATE INDEX IF NOT EXISTS idx_feedback_summary_date
    ON public."FeedbackSummary" (date DESC);

-- Safety events summary by type and severity
CREATE MATERIALIZED VIEW public."SafetyEventsSummary" AS
SELECT
    DATE_TRUNC('day', "timestamp") AS date,
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
CREATE MATERIALIZED VIEW public."SafetyEventsWithAnalysis" AS
SELECT
    e."event_id",
    e."timestamp" AS event_timestamp,
    e."event_type",
    e."event_classification",
    e."location",
    e."severity",
    e."description",
    e."patient_id",
    e."patient_mrn",
    e."patient_age_category",
    e."clinical_state",
    e."equipment_involved",
    e."harm_level",
    e."immediate_actions",
    e."root_causes",
    e."timeline_details",
    e."event_date",
    e."date_reported",
    e."rescue_attempted",
    e."patient_family_notified",
    e."increased_length_of_stay",
    e."time_harm_assessed",
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

-- Refresh materialized views function
CREATE OR REPLACE FUNCTION refresh_all_materialized_views()
RETURNS void AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY public."FeedbackSummary";
    REFRESH MATERIALIZED VIEW CONCURRENTLY public."SafetyEventsSummary";
    REFRESH MATERIALIZED VIEW CONCURRENTLY public."SafetyEventsWithAnalysis";
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_high_risk_events;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_feedback_summary;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_safety_events_by_location;
END;
$$ LANGUAGE plpgsql;

-- Grant permissions (adjust as needed)
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO postgres;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO postgres;
"""

        logger.info("Executing SQL initialization script")
        cursor.execute(sql_script)
        conn.commit()

        logger.info("Schema initialization completed successfully")

        cursor.close()
        conn.close()

        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Aurora schema initialized successfully'
            })
        }

    except Exception as error:
        logger.exception("Error initializing Aurora schema", extra={"error": str(error)})
        raise
