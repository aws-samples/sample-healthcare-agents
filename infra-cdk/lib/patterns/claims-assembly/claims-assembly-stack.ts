// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

/**
 * Claims Assembly Infrastructure Stack
 *
 * Creates supporting infrastructure for the Claims Assembly Agent system:
 * - S3 bucket for EDI 837P validation rules and requirements
 * - Bedrock Knowledge Base with OpenSearch Serverless for validation rule lookup
 * - IAM permissions for agent access
 *
 * This stack is designed to be imported and used by the main FAST CDK app.
 *
 * NOTE: Due to OpenSearch Serverless policy propagation timing issues with CloudFormation,
 * the Knowledge Base should be created manually via AWS Console after the collection is ready.
 * See MANUAL_KB_SETUP.md for step-by-step instructions.
 */

import * as cdk from 'aws-cdk-lib';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as bedrock from 'aws-cdk-lib/aws-bedrock';
import * as opensearchserverless from 'aws-cdk-lib/aws-opensearchserverless';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as kms from 'aws-cdk-lib/aws-kms';
import { Construct } from 'constructs';

export interface ClaimsAssemblyStackProps extends cdk.NestedStackProps {
  /**
   * Base name for the stack (e.g., "healthcare-agents-stack")
   * Used to prefix all resource names
   */
  readonly stackNameBase: string;

  /**
   * IAM role ARN that the AgentCore Runtime uses
   * This role will be granted permissions to access the Knowledge Base
   */
  readonly agentCoreRoleArn?: string;

  /**
   * KMS key for customer-managed encryption of S3 bucket
   * Required for HIPAA compliance
   */
  readonly dataEncryptionKey: kms.IKey;
}

export class ClaimsAssemblyStack extends cdk.NestedStack {
  /**
   * S3 bucket for storing EDI validation rules
   */
  public readonly validationBucket: s3.Bucket;

  /**
   * OpenSearch Serverless collection for vector search
   */
  public readonly opensearchCollection: opensearchserverless.CfnCollection;

  /**
   * Bedrock Knowledge Base (commented out - must be created manually)
   */
  // public readonly validationKnowledgeBase: bedrock.CfnKnowledgeBase;

  constructor(scope: Construct, id: string, props: ClaimsAssemblyStackProps) {
    const description = "Claims Assembly Infrastructure - S3 bucket, OpenSearch Serverless collection, and Bedrock Knowledge Base for EDI 837P validation rules and requirements";
    super(scope, id, { ...props, description });

    // ===== S3 Bucket for Validation Rules =====

    this.validationBucket = new s3.Bucket(this, 'ValidationBucket', {
      bucketName: `${props.stackNameBase}-claims-kb-${cdk.Aws.ACCOUNT_ID}`,
      removalPolicy: cdk.RemovalPolicy.RETAIN, // Retain for data safety
      autoDeleteObjects: false,
      versioned: true,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      encryptionKey: props.dataEncryptionKey,
      encryption: s3.BucketEncryption.KMS,
      lifecycleRules: [
        {
          id: 'TransitionOldVersions',
          enabled: true,
          noncurrentVersionTransitions: [
            {
              storageClass: s3.StorageClass.GLACIER,
              transitionAfter: cdk.Duration.days(90),
            },
          ],
        },
      ],
    });

    // ===== OpenSearch Serverless Infrastructure =====

    // Create encryption policy
    const encryptionPolicy = new opensearchserverless.CfnSecurityPolicy(
      this,
      'ValidationKBEncryptionPolicy',
      {
        name: `claims-kb-enc`,
        type: 'encryption',
        policy: JSON.stringify({
          Rules: [
            {
              ResourceType: 'collection',
              Resource: [`collection/claims-kb`],
            },
          ],
          AWSOwnedKey: true,
        }),
      }
    );

    // Create network policy
    const networkPolicy = new opensearchserverless.CfnSecurityPolicy(
      this,
      'ValidationKBNetworkPolicy',
      {
        name: `claims-kb-net`,
        type: 'network',
        policy: JSON.stringify([
          {
            Rules: [
              {
                ResourceType: 'collection',
                Resource: [`collection/claims-kb`],
              },
            ],
            AllowFromPublic: false,
            SourceServices: ['bedrock.amazonaws.com'],
          },
        ]),
      }
    );

    // Create OpenSearch Serverless collection
    this.opensearchCollection = new opensearchserverless.CfnCollection(
      this,
      'ValidationKBCollection',
      {
        name: `claims-kb`,
        type: 'VECTORSEARCH',
        description: 'Vector search collection for EDI 837P validation rules knowledge base',
      }
    );

    // Add dependencies
    this.opensearchCollection.addDependency(encryptionPolicy);
    this.opensearchCollection.addDependency(networkPolicy);

    // Create IAM role for Knowledge Base
    const kbRole = new iam.Role(this, 'ValidationKBRole', {
      roleName: `${props.stackNameBase}-claims-kb-role`,
      assumedBy: new iam.ServicePrincipal('bedrock.amazonaws.com'),
      description: 'Role for Bedrock Knowledge Base to access S3 and OpenSearch for validation rules',
    });

    // Grant S3 read permissions to KB role
    this.validationBucket.grantRead(kbRole);

    // Create data access policy for the KB role
    const dataAccessPolicy = new opensearchserverless.CfnAccessPolicy(
      this,
      'ValidationKBDataAccessPolicy',
      {
        name: `claims-kb-data`,
        type: 'data',
        policy: JSON.stringify([
          {
            Rules: [
              {
                ResourceType: 'collection',
                Resource: [`collection/claims-kb`],
                Permission: [
                  'aoss:DescribeCollectionItems',
                  'aoss:CreateCollectionItems',
                  'aoss:UpdateCollectionItems',
                ],
              },
              {
                ResourceType: 'index',
                Resource: [`index/claims-kb/*`],
                Permission: [
                  'aoss:DescribeIndex',
                  'aoss:ReadDocument',
                  'aoss:WriteDocument',
                  'aoss:CreateIndex',
                  'aoss:UpdateIndex',
                ],
              },
            ],
            Principal: [kbRole.roleArn],
          },
        ]),
      }
    );

    // Data access policy depends on collection
    dataAccessPolicy.addDependency(this.opensearchCollection);

    // ===== IAM Permissions for AgentCore Runtime =====

    // Grant AgentCore role access to Knowledge Base
    if (props.agentCoreRoleArn) {
      const agentCoreRole = iam.Role.fromRoleArn(
        this,
        'AgentCoreRole',
        props.agentCoreRoleArn
      );

      // Grant read access to S3 bucket
      this.validationBucket.grantRead(agentCoreRole);

      // Grant Bedrock Knowledge Base retrieve permissions
      // Note: Permissions are already granted by the nested stack to the agentCoreRole
      // This is a placeholder for additional KB-specific permissions if needed
    }

    // ===== SSM Parameters for Agent Access =====

    // Store bucket name in SSM
    new cdk.aws_ssm.StringParameter(this, 'ValidationBucketNameParam', {
      parameterName: `/${props.stackNameBase}/claims-assembly/validation_kb_bucket_name`,
      stringValue: this.validationBucket.bucketName,
      description: 'S3 bucket name for EDI validation rules knowledge base',
    });

    // Store collection endpoint in SSM
    new cdk.aws_ssm.StringParameter(this, 'CollectionEndpointParam', {
      parameterName: `/${props.stackNameBase}/claims-assembly/opensearch_endpoint`,
      stringValue: this.opensearchCollection.attrCollectionEndpoint,
      description: 'OpenSearch Serverless collection endpoint for validation KB',
    });

    // Store KB role ARN for manual KB creation
    new cdk.aws_ssm.StringParameter(this, 'KBRoleArnParam', {
      parameterName: `/${props.stackNameBase}/claims-assembly/kb_role_arn`,
      stringValue: kbRole.roleArn,
      description: 'IAM role ARN for Bedrock Knowledge Base (use for manual KB creation)',
    });

    // ===== Stack Outputs =====

    new cdk.CfnOutput(this, 'ValidationBucketName', {
      value: this.validationBucket.bucketName,
      description: 'S3 bucket for EDI validation rules knowledge base data',
      exportName: `${props.stackNameBase}-ClaimsValidationKBBucket`,
    });

    new cdk.CfnOutput(this, 'OpenSearchCollectionEndpoint', {
      value: this.opensearchCollection.attrCollectionEndpoint,
      description: 'OpenSearch Serverless collection endpoint',
      exportName: `${props.stackNameBase}-ClaimsKBCollectionEndpoint`,
    });

    new cdk.CfnOutput(this, 'ValidationKBRoleArn', {
      value: kbRole.roleArn,
      description: 'IAM role ARN for Validation Knowledge Base (use when creating KB manually)',
    });

    new cdk.CfnOutput(this, 'ManualSetupInstructions', {
      value: 'After stack deployment, create Validation Knowledge Base manually in AWS Console using the collection and role above. See MANUAL_KB_SETUP.md',
      description: 'Next steps for Validation Knowledge Base setup',
    });
  }

  /**
   * Grant the AgentCore Runtime role access to claims assembly resources
   *
   * @param role The IAM role used by AgentCore Runtime
   */
  public grantAgentAccess(role: iam.IRole): void {
    this.validationBucket.grantRead(role);

    // Grant Bedrock Knowledge Base retrieve permissions
    iam.Grant.addToPrincipal({
      grantee: role,
      actions: ['bedrock:Retrieve'],
      resourceArns: [
        `arn:aws:bedrock:${cdk.Aws.REGION}:${cdk.Aws.ACCOUNT_ID}:knowledge-base/*`,
      ],
    });
  }
}
