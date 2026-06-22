# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""
DynamoDB to Aurora PostgreSQL Safety Analysis Replication Lambda

This Lambda function replicates DynamoDB changes to Aurora PostgreSQL for hospital safety analytics
following the pattern from AWS Blog post:
https://aws.amazon.com/blogs/database/continuously-replicate-amazon-dynamodb-changes-to-amazon-aurora-postgresql-using-aws-lambda/

Event Types:
- INSERT: Creates new record in PostgreSQL
- MODIFY: Updates existing record in PostgreSQL
- REMOVE: Deletes record from PostgreSQL

Configuration via environment variables:
- DB_SECRET_ARN: Secrets Manager ARN for database credentials
- TABLE_NAME: Target PostgreSQL table name
- TABLE_MAPPING: JSON mapping of DynamoDB to PostgreSQL schema
"""

import json
import os
import re
import boto3
import psycopg2
from psycopg2 import sql
from aws_lambda_powertools import Logger
from aws_lambda_powertools.utilities import parameters

# Initialize Logger
logger = Logger()

# Initialize AWS clients
secrets_client = boto3.client('secretsmanager')
ssm_client = boto3.client('ssm')

# Allow only safe SQL identifier characters. Applied defensively even though
# values come from controlled environment variables / mapping configuration.
_IDENT_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')


def _safe_identifier(name: str, kind: str = "identifier") -> str:
    """Validate a SQL identifier before composing it into a query.

    Raises ValueError if the identifier contains unexpected characters.
    This is a defense-in-depth check in addition to psycopg2.sql composition.
    """
    if not isinstance(name, str) or not _IDENT_RE.match(name):
        raise ValueError(f"Invalid {kind}: {name!r}")
    return name


def get_db_connection():
    """Get database connection using credentials from Secrets Manager"""
    secret_arn = os.environ['DB_SECRET_ARN']

    # Retrieve secret from Secrets Manager
    secret_value = json.loads(parameters.get_secret(name=secret_arn))

    # Connect to PostgreSQL
    conn = psycopg2.connect(
        user=secret_value['username'],
        password=secret_value['password'],
        host=secret_value['host'],
        dbname=secret_value['dbname'],
        port=secret_value['port']
    )

    return conn


def get_table_mapping():
    """Get table mapping configuration from environment variable"""
    mapping_json = os.environ.get('TABLE_MAPPING', '{}')
    return json.loads(mapping_json)


def extract_dynamodb_value(item):
    """
    Extract value from DynamoDB attribute format

    Example:
    {'S': 'value'} -> 'value'
    {'N': '123'} -> 123
    {'BOOL': True} -> True
    """
    if 'S' in item:
        return item['S']
    elif 'N' in item:
        return int(item['N']) if '.' not in item['N'] else float(item['N'])
    elif 'BOOL' in item:
        return item['BOOL']
    elif 'NULL' in item:
        return None
    elif 'M' in item:
        # Map type - convert to JSON
        return json.dumps({k: extract_dynamodb_value(v) for k, v in item['M'].items()})
    elif 'L' in item:
        # List type - convert to JSON
        return json.dumps([extract_dynamodb_value(v) for v in item['L']])
    else:
        return str(item)


def process_insert(record, cursor, table_mapping):
    """Process INSERT event from DynamoDB stream"""
    logger.info("Processing INSERT event", extra={"record": record})

    table_name = _safe_identifier(os.environ['TABLE_NAME'], "table name")
    keys = record.get('dynamodb', {}).get('Keys', {})
    new_image = record.get('dynamodb', {}).get('NewImage', {})

    # Extract primary key
    pk_name = list(keys.keys())[0]
    pk_value = extract_dynamodb_value(keys[pk_name])

    # Build column list and values
    columns = []
    values = []

    for dynamo_attr, pg_col in table_mapping.items():
        if dynamo_attr in new_image:
            columns.append(_safe_identifier(pg_col, "column name"))
            values.append(extract_dynamodb_value(new_image[dynamo_attr]))

    # Build INSERT statement using psycopg2.sql for safe identifier composition
    stmt = sql.SQL("INSERT INTO {table} ({cols}) VALUES ({vals})").format(
        table=sql.Identifier(table_name),
        cols=sql.SQL(",").join(sql.Identifier(c) for c in columns),
        vals=sql.SQL(",").join(sql.Placeholder() * len(values)),
    )

    logger.info("Executing INSERT", extra={"table": table_name, "columns": columns})
    cursor.execute(stmt, values)
    logger.info("Record inserted successfully")


def process_modify(record, cursor, table_mapping):
    """Process MODIFY event from DynamoDB stream"""
    logger.info("Processing MODIFY event", extra={"record": record})

    table_name = _safe_identifier(os.environ['TABLE_NAME'], "table name")
    keys = record.get('dynamodb', {}).get('Keys', {})
    new_image = record.get('dynamodb', {}).get('NewImage', {})

    # Extract primary key
    pk_name = list(keys.keys())[0]
    pk_value = extract_dynamodb_value(keys[pk_name])
    pk_col = _safe_identifier(table_mapping.get(pk_name, pk_name), "primary key column")

    # Build SET clause
    set_cols = []
    values = []

    for dynamo_attr, pg_col in table_mapping.items():
        if dynamo_attr != pk_name and dynamo_attr in new_image:
            set_cols.append(_safe_identifier(pg_col, "column name"))
            values.append(extract_dynamodb_value(new_image[dynamo_attr]))

    # Add primary key to values for WHERE clause
    values.append(pk_value)

    # Build UPDATE statement using psycopg2.sql composition
    set_clause = sql.SQL(",").join(
        sql.SQL("{col} = {ph}").format(col=sql.Identifier(c), ph=sql.Placeholder())
        for c in set_cols
    )
    stmt = sql.SQL("UPDATE {table} SET {set_clause} WHERE {pk} = {ph}").format(
        table=sql.Identifier(table_name),
        set_clause=set_clause,
        pk=sql.Identifier(pk_col),
        ph=sql.Placeholder(),
    )

    logger.info("Executing UPDATE", extra={"table": table_name, "pk_col": pk_col})
    cursor.execute(stmt, values)
    logger.info("Record updated successfully")


def process_remove(record, cursor, table_mapping):
    """Process REMOVE event from DynamoDB stream"""
    logger.info("Processing REMOVE event", extra={"record": record})

    table_name = _safe_identifier(os.environ['TABLE_NAME'], "table name")
    keys = record.get('dynamodb', {}).get('Keys', {})

    # Extract primary key
    pk_name = list(keys.keys())[0]
    pk_value = extract_dynamodb_value(keys[pk_name])
    pk_col = _safe_identifier(table_mapping.get(pk_name, pk_name), "primary key column")

    # Build DELETE statement using psycopg2.sql composition
    stmt = sql.SQL("DELETE FROM {table} WHERE {pk} = {ph}").format(
        table=sql.Identifier(table_name),
        pk=sql.Identifier(pk_col),
        ph=sql.Placeholder(),
    )

    logger.info("Executing DELETE", extra={"table": table_name, "pk_col": pk_col})
    cursor.execute(stmt, (pk_value,))
    logger.info("Record deleted successfully")


@logger.inject_lambda_context(log_event=False)
def handler(event, context):
    """Lambda handler for DynamoDB stream events"""

    try:
        record_count = len(event.get('Records', []))
        event_names = [r['eventName'] for r in event.get('Records', [])]
        logger.info("Processing stream records", extra={"record_count": record_count, "event_names": event_names})

        # Get table mapping
        table_mapping = get_table_mapping()
        logger.info(f"Table mapping: {table_mapping}")

        # Connect to PostgreSQL
        conn = get_db_connection()
        cursor = conn.cursor()

        # Process each record in the stream
        for record in event['Records']:
            event_name = record['eventName']

            if event_name == 'INSERT':
                process_insert(record, cursor, table_mapping)
            elif event_name == 'MODIFY':
                process_modify(record, cursor, table_mapping)
            elif event_name == 'REMOVE':
                process_remove(record, cursor, table_mapping)
            else:
                logger.warning(f"Unknown event type: {event_name}")

        # Commit transaction
        conn.commit()
        logger.info(f"Successfully processed {len(event['Records'])} records")

        # Close connection
        cursor.close()
        conn.close()

        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': f'Successfully processed {len(event["Records"])} records'
            })
        }

    except (Exception, psycopg2.Error) as error:
        logger.exception("Error processing DynamoDB stream", extra={"error": str(error)})
        raise
