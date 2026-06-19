// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import * as cdk from 'aws-cdk-lib';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as bedrock from 'aws-cdk-lib/aws-bedrock';
import * as s3vectors from 'aws-cdk-lib/aws-s3vectors';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as kms from 'aws-cdk-lib/aws-kms';
import * as ssm from 'aws-cdk-lib/aws-ssm';
import { Construct } from 'constructs';

export interface MedicalCodingStackProps extends cdk.NestedStackProps {
  readonly stackNameBase: string;
  readonly agentCoreRoleArn?: string;
  readonly dataEncryptionKey: kms.IKey;
}

export class MedicalCodingStack extends cdk.NestedStack {
  public readonly knowledgeBaseBucket: s3.Bucket;
  public readonly knowledgeBase: bedrock.CfnKnowledgeBase;

  constructor(scope: Construct, id: string, props: MedicalCodingStackProps) {
    super(scope, id, {
      ...props,
      description: 'Medical Coding Infrastructure - S3 bucket and Bedrock Knowledge Base (S3 Vectors) for ICD-10, CPT, and HCPCS code semantic search',
    });

    this.knowledgeBaseBucket = new s3.Bucket(this, 'KnowledgeBaseBucket', {
      bucketName: `${props.stackNameBase}-medical-kb-${cdk.Aws.ACCOUNT_ID}`,
      removalPolicy: cdk.RemovalPolicy.RETAIN,
      versioned: true,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      encryptionKey: props.dataEncryptionKey,
      encryption: s3.BucketEncryption.KMS,
    });

    const vectorBucket = new s3vectors.CfnVectorBucket(this, 'VectorBucket3', {
      vectorBucketName: `${props.stackNameBase}-medical-vectors-${cdk.Aws.ACCOUNT_ID}`,
    });
    vectorBucket.applyRemovalPolicy(cdk.RemovalPolicy.RETAIN);

    const vectorIndex = new s3vectors.CfnIndex(this, 'VectorIndex3', {
      vectorBucketArn: vectorBucket.attrVectorBucketArn,
      indexName: 'medical-codes-index',
      dataType: 'float32',
      dimension: 1024,
      distanceMetric: 'cosine',
      metadataConfiguration: {
        nonFilterableMetadataKeys: ['AMAZON_BEDROCK_TEXT', 'AMAZON_BEDROCK_METADATA'],
      },
    });
    vectorIndex.applyRemovalPolicy(cdk.RemovalPolicy.RETAIN);
    vectorIndex.addDependency(vectorBucket);

    const kbRole = new iam.Role(this, 'KnowledgeBaseRole', {
      roleName: `${props.stackNameBase}-medical-kb-role`,
      assumedBy: new iam.ServicePrincipal('bedrock.amazonaws.com', {
        conditions: {
          StringEquals: { 'aws:SourceAccount': cdk.Aws.ACCOUNT_ID },
          ArnLike: { 'aws:SourceArn': `arn:aws:bedrock:${cdk.Aws.REGION}:${cdk.Aws.ACCOUNT_ID}:knowledge-base/*` },
        },
      }),
    });

    const kbPolicy = new iam.ManagedPolicy(this, 'KBPolicy', {
      roles: [kbRole],
      statements: [
        new iam.PolicyStatement({
          actions: ['s3:GetObject', 's3:ListBucket'],
          resources: [this.knowledgeBaseBucket.bucketArn, `${this.knowledgeBaseBucket.bucketArn}/*`],
        }),
        new iam.PolicyStatement({
          actions: ['kms:Decrypt', 'kms:GenerateDataKey'],
          resources: [props.dataEncryptionKey.keyArn],
        }),
        new iam.PolicyStatement({
          actions: [
            's3vectors:GetIndex', 's3vectors:ListIndexes',
            's3vectors:PutVectors', 's3vectors:GetVectors', 's3vectors:DeleteVectors',
            's3vectors:QueryVectors', 's3vectors:ListVectors', 's3vectors:GetVectorBucket',
          ],
          resources: [vectorBucket.attrVectorBucketArn, `${vectorBucket.attrVectorBucketArn}/index/*`],
        }),
        new iam.PolicyStatement({
          actions: ['bedrock:InvokeModel'],
          resources: [`arn:aws:bedrock:${cdk.Aws.REGION}::foundation-model/amazon.titan-embed-text-v2:0`],
        }),
      ],
    });

    this.knowledgeBase = new bedrock.CfnKnowledgeBase(this, 'KnowledgeBase3', {
      name: `${props.stackNameBase}-medical-kb`,
      description: 'Knowledge base for ICD-10-CM, CPT, and SNOMED CT codes',
      roleArn: kbRole.roleArn,
      knowledgeBaseConfiguration: {
        type: 'VECTOR',
        vectorKnowledgeBaseConfiguration: {
          embeddingModelArn: `arn:aws:bedrock:${cdk.Aws.REGION}::foundation-model/amazon.titan-embed-text-v2:0`,
        },
      },
      storageConfiguration: {
        type: 'S3_VECTORS',
        s3VectorsConfiguration: {
          vectorBucketArn: vectorBucket.attrVectorBucketArn,
          indexArn: vectorIndex.attrIndexArn,
        },
      },
    });
    this.knowledgeBase.addDependency(vectorIndex);
    this.knowledgeBase.addDependency(kbPolicy.node.defaultChild as cdk.CfnResource);

    new bedrock.CfnDataSource(this, 'DataSource3', {
      name: 'medical-codes-data-source',
      knowledgeBaseId: this.knowledgeBase.attrKnowledgeBaseId,
      dataSourceConfiguration: {
        type: 'S3',
        s3Configuration: { bucketArn: this.knowledgeBaseBucket.bucketArn },
      },
    }).addDependency(this.knowledgeBase);

    if (props.agentCoreRoleArn) {
      const agentCoreRole = iam.Role.fromRoleArn(this, 'AgentCoreRole', props.agentCoreRoleArn);
      this.knowledgeBaseBucket.grantRead(agentCoreRole);
      agentCoreRole.addToPrincipalPolicy(new iam.PolicyStatement({
        actions: ['bedrock:Retrieve'],
        resources: [this.knowledgeBase.attrKnowledgeBaseArn],
      }));
    }

    new ssm.StringParameter(this, 'KBBucketNameParam', {
      parameterName: `/${props.stackNameBase}/medical-coding/kb_bucket_name`,
      stringValue: this.knowledgeBaseBucket.bucketName,
    });
    new ssm.StringParameter(this, 'KBIdParam', {
      parameterName: `/${props.stackNameBase}/medical-coding/knowledge_base_id`,
      stringValue: this.knowledgeBase.attrKnowledgeBaseId,
    });

    new cdk.CfnOutput(this, 'KnowledgeBaseBucketName', {
      value: this.knowledgeBaseBucket.bucketName,
      exportName: `${props.stackNameBase}-MedicalCodesKBBucket`,
    });
    new cdk.CfnOutput(this, 'KnowledgeBaseId', { value: this.knowledgeBase.attrKnowledgeBaseId });
  }

  public grantAgentAccess(role: iam.IRole): void {
    this.knowledgeBaseBucket.grantRead(role);
    iam.Grant.addToPrincipal({
      grantee: role,
      actions: ['bedrock:Retrieve'],
      resourceArns: [`arn:aws:bedrock:${cdk.Aws.REGION}:${cdk.Aws.ACCOUNT_ID}:knowledge-base/*`],
    });
  }
}
