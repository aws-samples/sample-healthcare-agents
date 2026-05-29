// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

/**
 * Medical Coding Infrastructure Stack
 *
 * Creates supporting infrastructure for the Medical Coding Agent system:
 * - S3 bucket for medical codes and coding guidelines
 * - Bedrock Knowledge Base with OpenSearch Serverless for semantic search
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

export interface MedicalCodingStackProps extends cdk.NestedStackProps {
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

export class MedicalCodingStack extends cdk.NestedStack {
  /**
   * S3 bucket for storing medical codes and coding guidelines
   */
  public readonly knowledgeBaseBucket: s3.Bucket;

  /**
   * OpenSearch Serverless collection for vector search
   */
  public readonly opensearchCollection: opensearchserverless.CfnCollection;

  /**
   * Bedrock Knowledge Base (commented out - must be created manually)
   */
  // public readonly knowledgeBase: bedrock.CfnKnowledgeBase;

  constructor(scope: Construct, id: string, props: MedicalCodingStackProps) {
    const description = "Medical Coding Infrastructure - S3 bucket, OpenSearch Serverless collection, and Bedrock Knowledge Base for ICD-10, CPT, and HCPCS code semantic search";
    super(scope, id, { ...props, description });

    // ===== S3 Bucket for Medical Codes =====

    this.knowledgeBaseBucket = new s3.Bucket(this, 'KnowledgeBaseBucket', {
      bucketName: `${props.stackNameBase}-medical-kb-${cdk.Aws.ACCOUNT_ID}`,
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
      'KBCollectionEncryptionPolicy',
      {
        name: `medical-kb-enc`,
        type: 'encryption',
        policy: JSON.stringify({
          Rules: [
            {
              ResourceType: 'collection',
              Resource: [`collection/medical-kb`],
            },
          ],
          AWSOwnedKey: true,
        }),
      }
    );

    // Create network policy
    const networkPolicy = new opensearchserverless.CfnSecurityPolicy(
      this,
      'KBCollectionNetworkPolicy',
      {
        name: `medical-kb-net`,
        type: 'network',
        policy: JSON.stringify([
          {
            Rules: [
              {
                ResourceType: 'collection',
                Resource: [`collection/medical-kb`],
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
      'KBCollection',
      {
        name: `medical-kb`,
        type: 'VECTORSEARCH',
        description: 'Vector search collection for medical codes knowledge base',
      }
    );

    // Add dependencies
    this.opensearchCollection.addDependency(encryptionPolicy);
    this.opensearchCollection.addDependency(networkPolicy);

    // Create IAM role for Knowledge Base
    const kbRole = new iam.Role(this, 'KnowledgeBaseRole', {
      roleName: `${props.stackNameBase}-medical-kb-role`,
      assumedBy: new iam.ServicePrincipal('bedrock.amazonaws.com'),
      description: 'Role for Bedrock Knowledge Base to access S3 and OpenSearch',
    });

    // Grant S3 read permissions to KB role
    this.knowledgeBaseBucket.grantRead(kbRole);

    // Create data access policy for the KB role
    const dataAccessPolicy = new opensearchserverless.CfnAccessPolicy(
      this,
      'KBCollectionDataAccessPolicy',
      {
        name: `medical-kb-data`,
        type: 'data',
        policy: JSON.stringify([
          {
            Rules: [
              {
                ResourceType: 'collection',
                Resource: [`collection/medical-kb`],
                Permission: [
                  'aoss:DescribeCollectionItems',
                  'aoss:CreateCollectionItems',
                  'aoss:UpdateCollectionItems',
                ],
              },
              {
                ResourceType: 'index',
                Resource: [`index/medical-kb/*`],
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
      this.knowledgeBaseBucket.grantRead(agentCoreRole);

      // Grant Bedrock Knowledge Base retrieve permissions
      // Note: Permissions are already granted by the nested stack to the agentCoreRole
      // This is a placeholder for additional KB-specific permissions if needed
    }

    // ===== SSM Parameters for Agent Access =====

    // Store bucket name in SSM
    new cdk.aws_ssm.StringParameter(this, 'KBBucketNameParam', {
      parameterName: `/${props.stackNameBase}/medical-coding/kb_bucket_name`,
      stringValue: this.knowledgeBaseBucket.bucketName,
      description: 'S3 bucket name for medical codes knowledge base',
    });

    // Store collection endpoint in SSM
    new cdk.aws_ssm.StringParameter(this, 'CollectionEndpointParam', {
      parameterName: `/${props.stackNameBase}/medical-coding/opensearch_endpoint`,
      stringValue: this.opensearchCollection.attrCollectionEndpoint,
      description: 'OpenSearch Serverless collection endpoint for medical codes KB',
    });

    // Store KB role ARN for manual KB creation
    new cdk.aws_ssm.StringParameter(this, 'KBRoleArnParam', {
      parameterName: `/${props.stackNameBase}/medical-coding/kb_role_arn`,
      stringValue: kbRole.roleArn,
      description: 'IAM role ARN for Bedrock Knowledge Base (use for manual KB creation)',
    });

    // ===== Stack Outputs =====

    new cdk.CfnOutput(this, 'KnowledgeBaseBucketName', {
      value: this.knowledgeBaseBucket.bucketName,
      description: 'S3 bucket for medical codes knowledge base data',
      exportName: `${props.stackNameBase}-MedicalCodesKBBucket`,
    });

    new cdk.CfnOutput(this, 'OpenSearchCollectionEndpoint', {
      value: this.opensearchCollection.attrCollectionEndpoint,
      description: 'OpenSearch Serverless collection endpoint',
      exportName: `${props.stackNameBase}-MedicalKBCollectionEndpoint`,
    });

    new cdk.CfnOutput(this, 'KnowledgeBaseRoleArn', {
      value: kbRole.roleArn,
      description: 'IAM role ARN for Knowledge Base (use when creating KB manually)',
    });

    new cdk.CfnOutput(this, 'ManualSetupInstructions', {
      value: 'After stack deployment, create Knowledge Base manually in AWS Console using the collection and role above. See MANUAL_KB_SETUP.md',
      description: 'Next steps for Knowledge Base setup',
    });
  }

  /**
   * Grant the AgentCore Runtime role access to medical coding resources
   *
   * @param role The IAM role used by AgentCore Runtime
   */
  public grantAgentAccess(role: iam.IRole): void {
    this.knowledgeBaseBucket.grantRead(role);

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
