// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

/**
 * Safety Analysis Infrastructure Stack
 *
 * Creates Aurora Serverless v2 PostgreSQL cluster for safety analytics and reporting.
 * This cluster receives replicated data from DynamoDB tables via Lambda for
 * aggregation queries and business intelligence on hospital safety data.
 *
 * Security Features:
 * - Customer-managed KMS encryption for data at rest
 * - Secrets Manager for database credentials
 * - VPC isolation (deployed in private subnets)
 * - Automated backups with point-in-time recovery
 */

import * as cdk from 'aws-cdk-lib';
import * as rds from 'aws-cdk-lib/aws-rds';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as secretsmanager from 'aws-cdk-lib/aws-secretsmanager';
import * as kms from 'aws-cdk-lib/aws-kms';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as logs from 'aws-cdk-lib/aws-logs';
import { PythonFunction } from '@aws-cdk/aws-lambda-python-alpha';
import { DynamoEventSource } from 'aws-cdk-lib/aws-lambda-event-sources';
import { Construct } from 'constructs';
import * as path from 'path';

export interface SafetyAnalysisStackProps extends cdk.StackProps {
  /**
   * Base name for the stack (e.g., "healthcare-agents-stack")
   * Used to lookup DynamoDB tables via SSM parameters
   */
  readonly stackNameBase: string;

  /**
   * Optional: Which tables to replicate
   * If not specified, will attempt to replicate all tables found in SSM
   */
  readonly tablesToReplicate?: ('feedback' | 'events' | 'analysis')[];
}

export class SafetyAnalysisStack extends cdk.Stack {
  /**
   * KMS key for safety analysis data encryption
   */
  public readonly dataEncryptionKey: kms.IKey;
  /**
   * Aurora Serverless v2 cluster for safety analysis
   */
  public readonly cluster: rds.DatabaseCluster;

  /**
   * VPC for Aurora cluster
   */
  public readonly vpc: ec2.IVpc;

  /**
   * Database credentials secret
   */
  public readonly dbSecret: secretsmanager.ISecret;

  /**
   * Security group for Aurora cluster
   */
  public readonly dbSecurityGroup: ec2.SecurityGroup;

  constructor(scope: Construct, id: string, props: SafetyAnalysisStackProps) {
    const description = "Safety Analytics Stack - Aurora Serverless PostgreSQL cluster for hospital safety data aggregation and reporting with DynamoDB stream replication (v0.3.0) (uksb-v6dos0t5g8)";
    super(scope, id, { ...props, description });

    // Create customer-managed KMS key for safety analysis data encryption
    this.dataEncryptionKey = new kms.Key(this, "SafetyAnalysisEncryptionKey", {
      enableKeyRotation: true,
      description: "Customer-managed key for safety analysis data encryption (Aurora, DynamoDB streams)",
      alias: `${props.stackNameBase}-safety-analysis-key`,
      removalPolicy: cdk.RemovalPolicy.RETAIN, // Never delete key with encrypted data
      pendingWindow: cdk.Duration.days(30), // 30-day recovery window
    });

    // Create VPC for Aurora (or use existing VPC)
    // For simplicity, creating a new VPC with 2 AZs
    this.vpc = new ec2.Vpc(this, 'SafetyAnalysisVpc', {
      maxAzs: 2,
      natGateways: 1, // Reduce cost with single NAT gateway
      subnetConfiguration: [
        {
          cidrMask: 24,
          name: 'Public',
          subnetType: ec2.SubnetType.PUBLIC,
        },
        {
          cidrMask: 24,
          name: 'Private',
          subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS,
        },
        {
          cidrMask: 28,
          name: 'Isolated',
          subnetType: ec2.SubnetType.PRIVATE_ISOLATED,
        },
      ],
    });

    // Security group for Aurora cluster
    this.dbSecurityGroup = new ec2.SecurityGroup(this, 'AuroraSecurityGroup', {
      vpc: this.vpc,
      description: 'Security group for Aurora PostgreSQL cluster',
      allowAllOutbound: true,
    });

    // Allow Lambda to connect to Aurora
    this.dbSecurityGroup.addIngressRule(
      ec2.Peer.ipv4(this.vpc.vpcCidrBlock),
      ec2.Port.tcp(5432),
      'Allow PostgreSQL access from VPC'
    );

    // Create Aurora Serverless v2 cluster
    this.cluster = new rds.DatabaseCluster(this, 'AuroraCluster', {
      engine: rds.DatabaseClusterEngine.auroraPostgres({
        version: rds.AuroraPostgresEngineVersion.VER_15_8,
      }),
      clusterIdentifier: `${props.stackNameBase}-safety-analysis`,
      defaultDatabaseName: 'safety_analysis',
      writer: rds.ClusterInstance.serverlessV2('writer', {
        autoMinorVersionUpgrade: true,
        publiclyAccessible: false,
      }),
      readers: [
        // Add a reader instance for query scaling (optional)
        rds.ClusterInstance.serverlessV2('reader', {
          autoMinorVersionUpgrade: true,
          publiclyAccessible: false,
        }),
      ],
      serverlessV2MinCapacity: 0.5, // Minimum ACUs
      serverlessV2MaxCapacity: 2, // Maximum ACUs (keep low for cost control)
      vpc: this.vpc,
      vpcSubnets: {
        subnetType: ec2.SubnetType.PRIVATE_ISOLATED,
      },
      securityGroups: [this.dbSecurityGroup],
      storageEncryptionKey: this.dataEncryptionKey,
      backup: {
        retention: cdk.Duration.days(7),
        preferredWindow: '03:00-04:00', // Daily backup window
      },
      deletionProtection: false, // Set to true for production
      removalPolicy: cdk.RemovalPolicy.SNAPSHOT, // Create final snapshot on deletion
    });

    // Store the database secret
    this.dbSecret = this.cluster.secret!;

    // Store database connection details in SSM
    new cdk.aws_ssm.StringParameter(this, 'DbSecretArnParam', {
      parameterName: `/${props.stackNameBase}/safety_analysis/db_secret_arn`,
      stringValue: this.dbSecret.secretArn,
      description: 'Safety analysis Aurora database credentials secret ARN',
    });

    new cdk.aws_ssm.StringParameter(this, 'DbEndpointParam', {
      parameterName: `/${props.stackNameBase}/safety_analysis/db_endpoint`,
      stringValue: this.cluster.clusterEndpoint.hostname,
      description: 'Safety analysis Aurora cluster writer endpoint',
    });

    new cdk.aws_ssm.StringParameter(this, 'DbNameParam', {
      parameterName: `/${props.stackNameBase}/safety_analysis/db_name`,
      stringValue: 'safety_analysis',
      description: 'Safety analysis Aurora database name',
    });

    new cdk.aws_ssm.StringParameter(this, 'DbSecurityGroupIdParam', {
      parameterName: `/${props.stackNameBase}/safety_analysis/db_security_group_id`,
      stringValue: this.dbSecurityGroup.securityGroupId,
      description: 'Safety analysis Aurora security group ID',
    });

    // Store VPC subnet IDs for Lambda configuration
    new cdk.aws_ssm.StringParameter(this, 'VpcSubnetIdsParam', {
      parameterName: `/${props.stackNameBase}/safety_analysis/vpc_subnet_ids`,
      stringValue: this.vpc.privateSubnets.map(s => s.subnetId).join(','),
      description: 'VPC private subnet IDs for safety analysis Lambda',
    });

    // Outputs
    new cdk.CfnOutput(this, 'ClusterEndpoint', {
      value: this.cluster.clusterEndpoint.hostname,
      description: 'Aurora cluster writer endpoint',
      exportName: `${props.stackNameBase}-AuroraEndpoint`,
    });

    new cdk.CfnOutput(this, 'ClusterReadEndpoint', {
      value: this.cluster.clusterReadEndpoint.hostname,
      description: 'Aurora cluster reader endpoint',
      exportName: `${props.stackNameBase}-AuroraReadEndpoint`,
    });

    new cdk.CfnOutput(this, 'DatabaseName', {
      value: 'safety_analysis',
      description: 'Safety analysis Aurora database name',
    });

    new cdk.CfnOutput(this, 'SecretArn', {
      value: this.dbSecret.secretArn,
      description: 'Database credentials secret ARN',
    });

    // Create schema initialization Lambda (one-time use)
    this.createSchemaInitLambda(props.stackNameBase);

    // Create query Lambda for safety analytics
    this.createSafetyAnalyticsLambda(props.stackNameBase);

    // Lookup and create replication Lambda functions for available tables
    this.setupReplicationLambdas(props);
  }

  /**
   * Create one-time schema initialization Lambda
   */
  private createSchemaInitLambda(stackNameBase: string): void {
    // Security group for Lambda
    const lambdaSecurityGroup = new ec2.SecurityGroup(this, 'SchemaInitLambdaSG', {
      vpc: this.vpc,
      description: 'Security group for schema initialization Lambda',
      allowAllOutbound: true,
    });

    // Allow Lambda to connect to Aurora
    this.dbSecurityGroup.addIngressRule(
      lambdaSecurityGroup,
      ec2.Port.tcp(5432),
      'Allow schema init Lambda to connect to Aurora'
    );

    // Create Lambda function
    const initLambda = new PythonFunction(this, 'SchemaInitLambda', {
      functionName: `${stackNameBase}-init-safety-analysis-schema`,
      runtime: lambda.Runtime.PYTHON_3_12,
      entry: path.join(__dirname, '..', 'lambdas', 'safety-analytics', 'init-schema'),
      handler: 'handler',
      index: 'index.py',
      timeout: cdk.Duration.minutes(5),
      memorySize: 512,
      architecture: lambda.Architecture.X86_64,
      environment: {
        DB_SECRET_ARN: this.dbSecret.secretArn,
      },
      vpc: this.vpc,
      vpcSubnets: {
        subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS,
      },
      securityGroups: [lambdaSecurityGroup],
      layers: [
        lambda.LayerVersion.fromLayerVersionArn(
          this,
          'SchemaInitPowertoolsLayer',
          `arn:aws:lambda:${cdk.Stack.of(this).region}:017000801446:layer:AWSLambdaPowertoolsPythonV3-python312-x86_64:18`
        ),
      ],
      bundling: {
        buildArgs: {
          '--platform': 'linux/amd64',
        },
      },
      logGroup: new logs.LogGroup(this, 'SchemaInitLogGroup', {
        logGroupName: `/aws/lambda/${stackNameBase}-init-safety-analysis-schema`,
        retention: logs.RetentionDays.ONE_WEEK,
        removalPolicy: cdk.RemovalPolicy.DESTROY,
      }),
    });

    // Grant Lambda permissions
    this.dbSecret.grantRead(initLambda);

    // Output
    new cdk.CfnOutput(this, 'SchemaInitLambdaArn', {
      value: initLambda.functionArn,
      description: 'Schema initialization Lambda ARN (invoke once to create tables)',
    });

    new cdk.CfnOutput(this, 'SchemaInitCommand', {
      value: `aws lambda invoke --function-name ${stackNameBase}-init-safety-analysis-schema --profile quicksuite response.json && cat response.json`,
      description: 'Command to initialize safety analysis schema',
    });
  }

  /**
   * Create safety analytics query Lambda
   */
  private createSafetyAnalyticsLambda(stackNameBase: string): void {
    // Security group for Lambda
    const lambdaSecurityGroup = new ec2.SecurityGroup(this, 'SafetyAnalyticsLambdaSG', {
      vpc: this.vpc,
      description: 'Security group for safety analytics query Lambda',
      allowAllOutbound: true,
    });

    // Allow Lambda to connect to Aurora
    this.dbSecurityGroup.addIngressRule(
      lambdaSecurityGroup,
      ec2.Port.tcp(5432),
      'Allow safety analytics Lambda to connect to Aurora'
    );

    // Create Lambda function
    const analyticsLambda = new PythonFunction(this, 'SafetyAnalyticsLambda', {
      functionName: `${stackNameBase}-safety-analytics`,
      runtime: lambda.Runtime.PYTHON_3_12,
      entry: path.join(__dirname, '..', 'lambdas', 'safety-analytics', 'query'),
      handler: 'handler',
      index: 'index.py',
      timeout: cdk.Duration.seconds(30),
      memorySize: 512,
      architecture: lambda.Architecture.X86_64,
      environment: {
        DB_SECRET_ARN: this.dbSecret.secretArn,
      },
      vpc: this.vpc,
      vpcSubnets: {
        subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS,
      },
      securityGroups: [lambdaSecurityGroup],
      layers: [
        lambda.LayerVersion.fromLayerVersionArn(
          this,
          'SafetyAnalyticsPowertoolsLayer',
          `arn:aws:lambda:${cdk.Stack.of(this).region}:017000801446:layer:AWSLambdaPowertoolsPythonV3-python312-x86_64:18`
        ),
      ],
      bundling: {
        buildArgs: {
          '--platform': 'linux/amd64',
        },
      },
      logGroup: new logs.LogGroup(this, 'SafetyAnalyticsLogGroup', {
        logGroupName: `/aws/lambda/${stackNameBase}-safety-analytics`,
        retention: logs.RetentionDays.ONE_WEEK,
        removalPolicy: cdk.RemovalPolicy.DESTROY,
      }),
    });

    // Grant Lambda permissions
    this.dbSecret.grantRead(analyticsLambda);

    // Output
    new cdk.CfnOutput(this, 'SafetyAnalyticsLambdaArn', {
      value: analyticsLambda.functionArn,
      description: 'Safety analytics query Lambda ARN',
    });

    new cdk.CfnOutput(this, 'SafetyAnalyticsQueryCommand', {
      value: `aws lambda invoke --function-name ${stackNameBase}-safety-analytics --payload '{"sql_query": "SELECT COUNT(*) FROM public.\\\\"SafetyEvents\\\\""}' --profile quicksuite response.json && cat response.json`,
      description: 'Example command to query Aurora via Lambda',
    });
  }

  /**
   * Setup replication Lambda functions by looking up tables from SSM
   */
  private setupReplicationLambdas(props: SafetyAnalysisStackProps): void {
    const tablesToReplicate = props.tablesToReplicate || ['feedback', 'events', 'analysis'];

    // Feedback table replication
    if (tablesToReplicate.includes('feedback')) {
      const feedbackTableArn = cdk.aws_ssm.StringParameter.valueForStringParameter(
        this,
        `/${props.stackNameBase}/feedback_table_arn`
      );

      const feedbackTable = dynamodb.Table.fromTableAttributes(this, 'FeedbackTable', {
        tableArn: feedbackTableArn,
        tableStreamArn: cdk.aws_ssm.StringParameter.valueForStringParameter(
          this,
          `/${props.stackNameBase}/feedback_table_stream_arn`
        ),
      });

      this.createReplicationLambda('Feedback', feedbackTable, {
        feedbackId: 'feedback_id',
        sessionId: 'session_id',
        message: 'message',
        feedbackType: 'feedback_type',
        comment: 'comment',
        timestamp: 'timestamp',
      }, props.stackNameBase);
    }

    // Safety events table replication
    if (tablesToReplicate.includes('events')) {
      const eventsTableArn = cdk.aws_ssm.StringParameter.valueForStringParameter(
        this,
        `/${props.stackNameBase}/safety/events_table_arn`
      );

      const eventsTable = dynamodb.Table.fromTableAttributes(this, 'SafetyEventsTable', {
        tableArn: eventsTableArn,
        tableStreamArn: cdk.aws_ssm.StringParameter.valueForStringParameter(
          this,
          `/${props.stackNameBase}/safety/events_table_stream_arn`
        ),
      });

      this.createReplicationLambda('SafetyEvents', eventsTable, {
        event_id: 'event_id',
        timestamp: 'timestamp',
        event_type: 'event_type',
        location: 'location',
        severity: 'severity',
        description: 'description',
        patient_id: 'patient_id',
        patient_mrn: 'patient_mrn',
        clinical_state: 'clinical_state',
        equipment_involved: 'equipment_involved',
        harm_level: 'harm_level',
        immediate_actions: 'immediate_actions',
        root_causes: 'root_causes',
        timeline_details: 'timeline_details',
        event_date: 'event_date',
        date_reported: 'date_reported',
        event_classification: 'event_classification',
        patient_age_category: 'patient_age_category',
        rescue_attempted: 'rescue_attempted',
        patient_family_notified: 'patient_family_notified',
        increased_length_of_stay: 'increased_length_of_stay',
        time_harm_assessed: 'time_harm_assessed',
      }, props.stackNameBase);
    }

    // Safety analysis table replication
    if (tablesToReplicate.includes('analysis')) {
      const analysisTableArn = cdk.aws_ssm.StringParameter.valueForStringParameter(
        this,
        `/${props.stackNameBase}/safety/analysis_table_arn`
      );

      const analysisTable = dynamodb.Table.fromTableAttributes(this, 'SafetyAnalysisTable', {
        tableArn: analysisTableArn,
        tableStreamArn: cdk.aws_ssm.StringParameter.valueForStringParameter(
          this,
          `/${props.stackNameBase}/safety/analysis_table_stream_arn`
        ),
      });

      this.createReplicationLambda('SafetyAnalysis', analysisTable, {
        analysis_id: 'analysis_id',
        timestamp: 'timestamp',
        event_id: 'event_id',
        analyst_type: 'analyst_type',
        findings: 'findings',
        recommendations: 'recommendations',
        risk_score: 'risk_score',
      }, props.stackNameBase);
    }
  }

  /**
   * Create a Lambda function to replicate DynamoDB changes to Aurora
   */
  private createReplicationLambda(
    name: string,
    table: dynamodb.ITable,
    columnMapping: Record<string, string>,
    stackNameBase: string
  ): void {
    // Security group for Lambda
    const lambdaSecurityGroup = new ec2.SecurityGroup(this, `${name}LambdaSG`, {
      vpc: this.vpc,
      description: `Security group for ${name} replication Lambda`,
      allowAllOutbound: true,
    });

    // Allow Lambda to connect to Aurora
    this.dbSecurityGroup.addIngressRule(
      lambdaSecurityGroup,
      ec2.Port.tcp(5432),
      `Allow ${name} Lambda to connect to Aurora`
    );

    // Create Lambda function
    const replicatorLambda = new PythonFunction(this, `${name}ReplicatorLambda`, {
      functionName: `${stackNameBase}-${name.toLowerCase()}-replicator`,
      runtime: lambda.Runtime.PYTHON_3_12,
      entry: path.join(__dirname, '..', 'lambdas', 'safety-analytics', 'replicator'),
      handler: 'handler',
      index: 'index.py',
      timeout: cdk.Duration.minutes(5),
      memorySize: 512,
      architecture: lambda.Architecture.X86_64, // Use x86_64 for better psycopg2 support
      environment: {
        DB_SECRET_ARN: this.dbSecret.secretArn,
        TABLE_NAME: `public."${name}"`,
        TABLE_MAPPING: JSON.stringify(columnMapping),
      },
      vpc: this.vpc,
      vpcSubnets: {
        subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS,
      },
      securityGroups: [lambdaSecurityGroup],
      layers: [
        lambda.LayerVersion.fromLayerVersionArn(
          this,
          `${name}PowertoolsLayer`,
          `arn:aws:lambda:${cdk.Stack.of(this).region}:017000801446:layer:AWSLambdaPowertoolsPythonV3-python312-x86_64:18`
        ),
      ],
      bundling: {
        // Use Docker platform matching Lambda runtime for psycopg2-binary compilation
        buildArgs: {
          '--platform': 'linux/amd64',
        },
      },
      logGroup: new logs.LogGroup(this, `${name}ReplicatorLogGroup`, {
        logGroupName: `/aws/lambda/${stackNameBase}-${name.toLowerCase()}-replicator`,
        retention: logs.RetentionDays.ONE_WEEK,
        removalPolicy: cdk.RemovalPolicy.DESTROY,
      }),
    });

    // Grant Lambda permissions
    this.dbSecret.grantRead(replicatorLambda);
    table.grantStreamRead(replicatorLambda);

    // Grant KMS decrypt permission for DynamoDB stream encryption
    // The table.grantStreamRead() doesn't grant KMS permissions when using fromTableAttributes
    replicatorLambda.addToRolePolicy(new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: ['kms:Decrypt'],
      resources: ['*'], // Will be scoped to DynamoDB table's KMS key
    }));

    // Add DynamoDB stream as event source
    replicatorLambda.addEventSource(
      new DynamoEventSource(table, {
        startingPosition: lambda.StartingPosition.LATEST,
        batchSize: 100,
        bisectBatchOnError: true,
        retryAttempts: 3,
      })
    );

    // Output
    new cdk.CfnOutput(this, `${name}ReplicatorLambdaArn`, {
      value: replicatorLambda.functionArn,
      description: `${name} replication Lambda ARN`,
    });
  }
}
