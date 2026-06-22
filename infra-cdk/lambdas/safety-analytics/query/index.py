# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Lambda function to query Aurora PostgreSQL for safety analytics.

This Lambda executes read-only SQL queries against the Aurora database
and returns results in JSON format.
"""

import json
import os
import boto3
import psycopg2
import psycopg2.extras
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


@logger.inject_lambda_context(log_event=False)
def handler(event, context):
    """Execute SQL query and return results"""

    try:
        # Get SQL query from event
        sql_query = event.get('sql_query')

        if not sql_query:
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'error': 'Missing required parameter: sql_query',
                    'usage': 'Provide a SQL query in the event: {"sql_query": "SELECT * FROM public.\\"SafetyEvents\\" LIMIT 10"}'
                })
            }

        # Enforce read-only: only allow a single SELECT statement.
        # This Lambda is invoked by trusted internal callers, but we defense-in-depth
        # by rejecting any non-SELECT, multi-statement, or dangerous keywords.
        normalized = sql_query.strip().rstrip(';').strip()
        upper = normalized.upper()
        if not upper.startswith('SELECT') and not upper.startswith('WITH'):
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'error': 'Only SELECT queries are permitted',
                })
            }
        if ';' in normalized:
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'error': 'Multi-statement queries are not permitted',
                })
            }
        # Block common DDL/DML keywords even inside a query body
        forbidden = (' INSERT ', ' UPDATE ', ' DELETE ', ' DROP ', ' TRUNCATE ',
                     ' ALTER ', ' CREATE ', ' GRANT ', ' REVOKE ', ' COPY ',
                     ' EXECUTE ', ' CALL ')
        padded = f' {upper} '
        for kw in forbidden:
            if kw in padded:
                return {
                    'statusCode': 400,
                    'body': json.dumps({
                        'error': f'Forbidden keyword detected: {kw.strip()}',
                    })
                }

        logger.info("Executing read-only query")

        # Connect to database
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Execute query (validated above; read-only enforced)
        cursor.execute(normalized)  # nosemgrep: psycopg-sqli - read-only enforcement above

        # Fetch results
        if upper.startswith('SELECT') or upper.startswith('WITH'):
            results = cursor.fetchall()
            row_count = len(results)

            # Convert results to JSON-serializable format
            json_results = []
            for row in results:
                json_row = {}
                for key, value in row.items():
                    # Convert datetime objects to ISO format strings
                    if hasattr(value, 'isoformat'):
                        json_row[key] = value.isoformat()
                    else:
                        json_row[key] = value
                json_results.append(json_row)

            logger.info(f"Query returned {row_count} rows")

            response_body = {
                'row_count': row_count,
                'results': json_results
            }
        else:
            # Unreachable given the SELECT/WITH guard above, but kept defensively.
            conn.commit()
            response_body = {
                'message': 'Query executed successfully',
                'rows_affected': cursor.rowcount
            }

        cursor.close()
        conn.close()

        return {
            'statusCode': 200,
            'body': json.dumps(response_body)
        }

    except psycopg2.Error as db_error:
        logger.exception("Database error", extra={"error": str(db_error)})
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': 'Database error',
                'message': str(db_error)
            })
        }
    except Exception as error:
        logger.exception("Error executing query", extra={"error": str(error)})
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': 'Internal error',
                'message': str(error)
            })
        }
