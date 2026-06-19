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

export interface ClaimsAssemblyStackProps extends cdk.NestedStackProps {
  readonly stackNameBase: string;
  readonly agentCoreRoleArn?: string;
  readonly dataEncryptionKey: kms.IKey;
}

export class ClaimsAssemblyStack extends cdk.NestedStack {
  public readonly validationBucket: s3.Bucket;
  public readonly knowledgeBase: bedrock.CfnKnowledgeBase;

  constructor(scope: Construct, id: string, props: ClaimsAssemblyStackProps) {
    super(scope, id, {
      ...props,
      description: 'Claims Assembly Infrastructure - S3 bucket and Bedrock Knowledge Base (S3 Vectors) for EDI 837P validation rules',
    });

    this.validationBucket = new s3.Bucket(this, 'ValidationBucket', {
      bucketName: `${props.stackNameBase}-claims-kb-${cdk.Aws.ACCOUNT_ID}`,
      removalPolicy: cdk.RemovalPolicy.RETAIN,
      versioned: true,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      encryptionKey: props.dataEncryptionKey,
      encryption: s3.BucketEncryption.KMS,
    });

    const vectorBucket = new s3vectors.CfnVectorBucket(this, 'VectorBucket3', {
      vectorBucketName: `${props.stackNameBase}-claims-vectors-${cdk.Aws.ACCOUNT_ID}`,
    });
    vectorBucket.applyRemovalPolicy(cdk.RemovalPolicy.RETAIN);

    const vectorIndex = new s3vectors.CfnIndex(this, 'VectorIndex3', {
      vectorBucketName: `${props.stackNameBase}-claims-vectors-${cdk.Aws.ACCOUNT_ID}`,
      indexName: 'validation-rules-index',
      dataType: 'float32',
      dimension: 1024,
      distanceMetric: 'cosine',
      metadataConfiguration: {
        nonFilterableMetadataKeys: ['AMAZON_BEDROCK_TEXT', 'AMAZON_BEDROCK_METADATA'],
      },
    });
    vectorIndex.applyRemovalPolicy(cdk.RemovalPolicy.RETAIN);
    vectorIndex.addDependency(vectorBucket);

    const kbRole = new iam.Role(this, 'ValidationKBRole', {
      roleName: `${props.stackNameBase}-claims-kb-role`,
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
          resources: [this.validationBucket.bucketArn, `${this.validationBucket.bucketArn}/*`],
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

    this.knowledgeBase = new bedrock.CfnKnowledgeBase(this, 'ValidationKB3', {
      name: `${props.stackNameBase}-claims-kb`,
      description: 'Knowledge base for EDI 837P payer validation rules and HIPAA compliance',
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

    const dataSource = new bedrock.CfnDataSource(this, 'DataSource3', {
      name: 'validation-rules-data-source',
      knowledgeBaseId: this.knowledgeBase.attrKnowledgeBaseId,
      dataSourceConfiguration: {
        type: 'S3',
        s3Configuration: { bucketArn: this.validationBucket.bucketArn },
      },
    });
    dataSource.addDependency(this.knowledgeBase);

    if (props.agentCoreRoleArn) {
      const agentCoreRole = iam.Role.fromRoleArn(this, 'AgentCoreRole', props.agentCoreRoleArn);
      this.validationBucket.grantRead(agentCoreRole);
      agentCoreRole.addToPrincipalPolicy(new iam.PolicyStatement({
        actions: ['bedrock:Retrieve'],
        resources: [this.knowledgeBase.attrKnowledgeBaseArn],
      }));
    }

    new ssm.StringParameter(this, 'ValidationBucketNameParam', {
      parameterName: `/${props.stackNameBase}/claims-assembly/validation_kb_bucket_name`,
      stringValue: this.validationBucket.bucketName,
    });
    new ssm.StringParameter(this, 'ValidationKBIdParam', {
      parameterName: `/${props.stackNameBase}/validation-kb-id`,
      stringValue: this.knowledgeBase.attrKnowledgeBaseId,
    });

    new cdk.CfnOutput(this, 'ValidationBucketName', {
      value: this.validationBucket.bucketName,
      exportName: `${props.stackNameBase}-ClaimsValidationKBBucket`,
    });
    new cdk.CfnOutput(this, 'ValidationKnowledgeBaseId', { value: this.knowledgeBase.attrKnowledgeBaseId });
  }

  public grantAgentAccess(role: iam.IRole): void {
    this.validationBucket.grantRead(role);
    iam.Grant.addToPrincipal({
      grantee: role,
      actions: ['bedrock:Retrieve'],
      resourceArns: [`arn:aws:bedrock:${cdk.Aws.REGION}:${cdk.Aws.ACCOUNT_ID}:knowledge-base/*`],
    });
  }
}
