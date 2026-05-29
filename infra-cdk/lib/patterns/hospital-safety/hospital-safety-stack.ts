// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

/**
 * Hospital Safety Infrastructure Stack
 *
 * Creates supporting infrastructure for the Hospital Safety Agent system:
 * - DynamoDB tables for events and analysis storage
 * - SNS topic for critical alerts
 * - IAM permissions for agent access
 *
 * This stack is designed to be imported and used by the main FAST CDK app.
 */

import * as cdk from 'aws-cdk-lib';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import * as sns from 'aws-cdk-lib/aws-sns';
import * as subscriptions from 'aws-cdk-lib/aws-sns-subscriptions';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as kms from 'aws-cdk-lib/aws-kms';
import { Construct } from 'constructs';

export interface HospitalSafetyStackProps extends cdk.NestedStackProps {
  /**
   * Base name for the stack (e.g., "healthcare-agents-stack")
   * Used to prefix all resource names
   */
  readonly stackNameBase: string;

  /**
   * Email address for safety officers to receive all alerts
   * Default: safety@example.com
   */
  readonly safetyOfficerEmail?: string;

  /**
   * Email address for physicians to receive immediate high/critical alerts
   * Default: physician@example.com
   */
  readonly physicianEmail?: string;

  /**
   * IAM role ARN that the AgentCore Runtime uses
   * This role will be granted permissions to access DynamoDB and SNS
   */
  readonly agentCoreRoleArn?: string;

  /**
   * KMS key for customer-managed encryption of DynamoDB tables and SNS topic
   * Required for HIPAA compliance
   */
  readonly dataEncryptionKey: kms.IKey;
}

export class HospitalSafetyStack extends cdk.NestedStack {
  /**
   * DynamoDB table for storing safety events
   */
  public readonly eventsTable: dynamodb.Table;

  /**
   * DynamoDB table for storing specialist analysis results
   */
  public readonly analysisTable: dynamodb.Table;

  /**
   * SNS topic for critical safety alerts
   */
  public readonly alertTopic: sns.Topic;

  constructor(scope: Construct, id: string, props: HospitalSafetyStackProps) {
    const description = "Hospital Safety Infrastructure - DynamoDB tables (events, analysis), SNS alerts, and IAM permissions for multi-agent safety monitoring system";
    super(scope, id, { ...props, description });

    // ===== DynamoDB Tables =====

    // Events Table: Stores all safety events
    this.eventsTable = new dynamodb.Table(this, 'SafetyEventsTable', {
      tableName: `${props.stackNameBase}-safety-events`,
      partitionKey: {
        name: 'event_id',
        type: dynamodb.AttributeType.STRING,
      },
      sortKey: {
        name: 'timestamp',
        type: dynamodb.AttributeType.STRING,
      },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      pointInTimeRecovery: true,
      encryption: dynamodb.TableEncryption.CUSTOMER_MANAGED,
      encryptionKey: props.dataEncryptionKey,
      removalPolicy: cdk.RemovalPolicy.RETAIN, // Retain for safety/compliance
      stream: dynamodb.StreamViewType.NEW_IMAGE, // Enable streams for Aurora replication
    });

    // Add GSI for querying by event type
    this.eventsTable.addGlobalSecondaryIndex({
      indexName: 'event-type-index',
      partitionKey: {
        name: 'event_type',
        type: dynamodb.AttributeType.STRING,
      },
      sortKey: {
        name: 'timestamp',
        type: dynamodb.AttributeType.STRING,
      },
    });

    // Add GSI for querying by location (for infection pattern analysis)
    this.eventsTable.addGlobalSecondaryIndex({
      indexName: 'location-index',
      partitionKey: {
        name: 'location',
        type: dynamodb.AttributeType.STRING,
      },
      sortKey: {
        name: 'timestamp',
        type: dynamodb.AttributeType.STRING,
      },
    });

    // Analysis Table: Stores specialist agent analysis results
    this.analysisTable = new dynamodb.Table(this, 'SafetyAnalysisTable', {
      tableName: `${props.stackNameBase}-safety-analysis`,
      partitionKey: {
        name: 'analysis_id',
        type: dynamodb.AttributeType.STRING,
      },
      sortKey: {
        name: 'timestamp',
        type: dynamodb.AttributeType.STRING,
      },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      pointInTimeRecovery: true,
      encryption: dynamodb.TableEncryption.CUSTOMER_MANAGED,
      encryptionKey: props.dataEncryptionKey,
      removalPolicy: cdk.RemovalPolicy.RETAIN,
      stream: dynamodb.StreamViewType.NEW_IMAGE, // Enable streams for Aurora replication
    });

    // Add GSI for querying analysis by event_id
    this.analysisTable.addGlobalSecondaryIndex({
      indexName: 'event-id-index',
      partitionKey: {
        name: 'event_id',
        type: dynamodb.AttributeType.STRING,
      },
      sortKey: {
        name: 'timestamp',
        type: dynamodb.AttributeType.STRING,
      },
    });

    // ===== SNS Topic for Alerts =====

    this.alertTopic = new sns.Topic(this, 'SafetyAlertTopic', {
      topicName: `${props.stackNameBase}-safety-alerts`,
      displayName: 'Hospital Safety Critical Alerts',
      masterKey: props.dataEncryptionKey, // HIPAA Compliance: CMK encryption
    });

    // Subscribe safety officer email (receives all alerts)
    const safetyOfficerEmail = props.safetyOfficerEmail || 'safety@example.com';
    this.alertTopic.addSubscription(
      new subscriptions.EmailSubscription(safetyOfficerEmail)
    );

    // Subscribe physician email (receives immediate high/critical alerts)
    const physicianEmail = props.physicianEmail || 'physician@example.com';
    this.alertTopic.addSubscription(
      new subscriptions.EmailSubscription(physicianEmail)
    );

    // ===== IAM Permissions =====

    // If AgentCore role ARN is provided, grant it access to tables and SNS
    if (props.agentCoreRoleArn) {
      const agentCoreRole = iam.Role.fromRoleArn(
        this,
        'AgentCoreRole',
        props.agentCoreRoleArn
      );

      // Grant read/write access to DynamoDB tables
      this.eventsTable.grantReadWriteData(agentCoreRole);
      this.analysisTable.grantReadWriteData(agentCoreRole);

      // Grant publish access to SNS topic
      this.alertTopic.grantPublish(agentCoreRole);
    }

    // ===== SSM Parameters for Agent Access =====

    // Store table names in SSM for agent runtime access
    new cdk.aws_ssm.StringParameter(this, 'EventsTableNameParam', {
      parameterName: `/${props.stackNameBase}/safety/events_table_name`,
      stringValue: this.eventsTable.tableName,
      description: 'DynamoDB table name for hospital safety events',
    });

    new cdk.aws_ssm.StringParameter(this, 'AnalysisTableNameParam', {
      parameterName: `/${props.stackNameBase}/safety/analysis_table_name`,
      stringValue: this.analysisTable.tableName,
      description: 'DynamoDB table name for safety analysis results',
    });

    // Store table ARNs in SSM for safety-analysis stack lookup
    new cdk.aws_ssm.StringParameter(this, 'EventsTableArnParam', {
      parameterName: `/${props.stackNameBase}/safety/events_table_arn`,
      stringValue: this.eventsTable.tableArn,
      description: 'DynamoDB table ARN for hospital safety events',
    });

    new cdk.aws_ssm.StringParameter(this, 'AnalysisTableArnParam', {
      parameterName: `/${props.stackNameBase}/safety/analysis_table_arn`,
      stringValue: this.analysisTable.tableArn,
      description: 'DynamoDB table ARN for safety analysis results',
    });

    // Store table stream ARNs for replication
    new cdk.aws_ssm.StringParameter(this, 'EventsTableStreamArnParam', {
      parameterName: `/${props.stackNameBase}/safety/events_table_stream_arn`,
      stringValue: this.eventsTable.tableStreamArn!,
      description: 'DynamoDB table stream ARN for hospital safety events',
    });

    new cdk.aws_ssm.StringParameter(this, 'AnalysisTableStreamArnParam', {
      parameterName: `/${props.stackNameBase}/safety/analysis_table_stream_arn`,
      stringValue: this.analysisTable.tableStreamArn!,
      description: 'DynamoDB table stream ARN for safety analysis results',
    });

    new cdk.aws_ssm.StringParameter(this, 'AlertTopicArnParam', {
      parameterName: `/${props.stackNameBase}/safety/alert_topic_arn`,
      stringValue: this.alertTopic.topicArn,
      description: 'SNS topic ARN for critical safety alerts',
    });

    // ===== Stack Outputs =====

    new cdk.CfnOutput(this, 'EventsTableName', {
      value: this.eventsTable.tableName,
      description: 'DynamoDB table for safety events',
      exportName: `${props.stackNameBase}-SafetyEventsTable`,
    });

    new cdk.CfnOutput(this, 'AnalysisTableName', {
      value: this.analysisTable.tableName,
      description: 'DynamoDB table for safety analysis',
      exportName: `${props.stackNameBase}-SafetyAnalysisTable`,
    });

    new cdk.CfnOutput(this, 'AlertTopicArn', {
      value: this.alertTopic.topicArn,
      description: 'SNS topic for critical alerts',
      exportName: `${props.stackNameBase}-SafetyAlertTopic`,
    });

    new cdk.CfnOutput(this, 'SafetyOfficerEmail', {
      value: safetyOfficerEmail,
      description: 'Safety officer email (receives all alerts)',
    });

    new cdk.CfnOutput(this, 'PhysicianEmail', {
      value: physicianEmail,
      description: 'Physician email (receives immediate high/critical alerts)',
    });
  }

  /**
   * Grant the AgentCore Runtime role access to all hospital safety resources
   *
   * Call this method after creating the AgentCore Runtime to ensure the agent
   * has permissions to access DynamoDB and SNS.
   *
   * @param role The IAM role used by AgentCore Runtime
   */
  public grantAgentAccess(role: iam.IRole): void {
    this.eventsTable.grantReadWriteData(role);
    this.analysisTable.grantReadWriteData(role);
    this.alertTopic.grantPublish(role);
  }
}
