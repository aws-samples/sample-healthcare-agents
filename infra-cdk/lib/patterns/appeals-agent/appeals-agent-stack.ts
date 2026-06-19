// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import * as cdk from "aws-cdk-lib"
import * as s3 from "aws-cdk-lib/aws-s3"
import * as iam from "aws-cdk-lib/aws-iam"
import * as kms from "aws-cdk-lib/aws-kms"
import * as ssm from "aws-cdk-lib/aws-ssm"
import * as bedrock from "aws-cdk-lib/aws-bedrock"
import * as s3vectors from "aws-cdk-lib/aws-s3vectors"
import { Construct } from "constructs"

export interface AppealsAgentStackProps extends cdk.NestedStackProps {
  readonly stackNameBase: string
  readonly agentCoreRoleArn?: string
  readonly dataEncryptionKey: kms.IKey
}

export class AppealsAgentStack extends cdk.NestedStack {
  public readonly appealsBucket: s3.Bucket
  public readonly knowledgeBase: bedrock.CfnKnowledgeBase

  constructor(scope: Construct, id: string, props: AppealsAgentStackProps) {
    super(scope, id, {
      ...props,
      description: "Appeals Agent Infrastructure - S3 appeals bucket and Bedrock Knowledge Base (S3 Vectors) for denial codes and appeal regulations",
    })

    this.appealsBucket = new s3.Bucket(this, "AppealsBucket", {
      bucketName: `${props.stackNameBase}-appeals-letters-${cdk.Aws.ACCOUNT_ID}`,
      encryptionKey: props.dataEncryptionKey,
      encryption: s3.BucketEncryption.KMS,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      removalPolicy: cdk.RemovalPolicy.RETAIN,
      versioned: true,
      lifecycleRules: [{ id: "ExpireOldLetters", enabled: true, expiration: cdk.Duration.days(365) }],
    })

    new ssm.StringParameter(this, "AppealsBucketParam", {
      parameterName: `/${props.stackNameBase}/appeals-bucket`,
      stringValue: this.appealsBucket.bucketName,
    })

    const kbDataBucket = new s3.Bucket(this, "AppealsKBDataBucket", {
      bucketName: `${props.stackNameBase}-appeals-kb-${cdk.Aws.ACCOUNT_ID}`,
      encryption: s3.BucketEncryption.S3_MANAGED,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      removalPolicy: cdk.RemovalPolicy.RETAIN,
      versioned: true,
    })

    new ssm.StringParameter(this, "AppealsKBDataBucketParam", {
      parameterName: `/${props.stackNameBase}/appeals-kb-data-bucket`,
      stringValue: kbDataBucket.bucketName,
    })

    const vectorBucket = new s3vectors.CfnVectorBucket(this, "AppealsVectorBucket3", {
      vectorBucketName: `${props.stackNameBase}-appeals-vectors-${cdk.Aws.ACCOUNT_ID}`,
    })
    vectorBucket.applyRemovalPolicy(cdk.RemovalPolicy.RETAIN)

    const vectorIndex = new s3vectors.CfnIndex(this, "AppealsVectorIndex3", {
      vectorBucketArn: vectorBucket.attrVectorBucketArn,
      indexName: "appeals-index",
      dataType: "float32",
      dimension: 1024,
      distanceMetric: "cosine",
      metadataConfiguration: {
        nonFilterableMetadataKeys: ["AMAZON_BEDROCK_TEXT", "AMAZON_BEDROCK_METADATA"],
      },
    })
    vectorIndex.applyRemovalPolicy(cdk.RemovalPolicy.RETAIN)
    vectorIndex.addDependency(vectorBucket)

    const kbRole = new iam.Role(this, "AppealsKBRole", {
      roleName: `${props.stackNameBase}-appeals-kb-role`,
      assumedBy: new iam.ServicePrincipal("bedrock.amazonaws.com", {
        conditions: {
          StringEquals: { "aws:SourceAccount": cdk.Aws.ACCOUNT_ID },
          ArnLike: { "aws:SourceArn": `arn:aws:bedrock:${cdk.Aws.REGION}:${cdk.Aws.ACCOUNT_ID}:knowledge-base/*` },
        },
      }),
    })

    const kbPolicy = new iam.ManagedPolicy(this, "AppealsKBPolicy", {
      roles: [kbRole],
      statements: [
        new iam.PolicyStatement({
          actions: ["s3:GetObject", "s3:ListBucket"],
          resources: [kbDataBucket.bucketArn, `${kbDataBucket.bucketArn}/*`],
        }),
        new iam.PolicyStatement({
          actions: [
            "s3vectors:GetIndex", "s3vectors:ListIndexes",
            "s3vectors:PutVectors", "s3vectors:GetVectors", "s3vectors:DeleteVectors",
            "s3vectors:QueryVectors", "s3vectors:ListVectors", "s3vectors:GetVectorBucket",
          ],
          resources: [vectorBucket.attrVectorBucketArn, `${vectorBucket.attrVectorBucketArn}/index/*`],
        }),
        new iam.PolicyStatement({
          actions: ["bedrock:InvokeModel"],
          resources: [`arn:aws:bedrock:${cdk.Aws.REGION}::foundation-model/amazon.titan-embed-text-v2:0`],
        }),
      ],
    })

    this.knowledgeBase = new bedrock.CfnKnowledgeBase(this, "AppealsKB3", {
      name: `${props.stackNameBase}-appeals-kb`,
      description: "Knowledge base for appeal denial codes, regulations, and clinical guidelines",
      roleArn: kbRole.roleArn,
      knowledgeBaseConfiguration: {
        type: "VECTOR",
        vectorKnowledgeBaseConfiguration: {
          embeddingModelArn: `arn:aws:bedrock:${cdk.Aws.REGION}::foundation-model/amazon.titan-embed-text-v2:0`,
        },
      },
      storageConfiguration: {
        type: "S3_VECTORS",
        s3VectorsConfiguration: {
          vectorBucketArn: vectorBucket.attrVectorBucketArn,
          indexArn: vectorIndex.attrIndexArn,
        },
      },
    })
    this.knowledgeBase.addDependency(vectorIndex)
    this.knowledgeBase.addDependency(kbPolicy.node.defaultChild as cdk.CfnResource)

    const dataSource = new bedrock.CfnDataSource(this, "AppealsKBDataSource3", {
      name: "appeals-data-source",
      knowledgeBaseId: this.knowledgeBase.attrKnowledgeBaseId,
      dataSourceConfiguration: {
        type: "S3",
        s3Configuration: { bucketArn: kbDataBucket.bucketArn },
      },
    })
    dataSource.addDependency(this.knowledgeBase)

    if (props.agentCoreRoleArn) {
      const agentRole = iam.Role.fromRoleArn(this, "AgentCoreRole", props.agentCoreRoleArn)
      this.appealsBucket.grantReadWrite(agentRole)
      kbDataBucket.grantRead(agentRole)
      agentRole.addToPrincipalPolicy(new iam.PolicyStatement({
        actions: ["bedrock:Retrieve"],
        resources: [this.knowledgeBase.attrKnowledgeBaseArn],
      }))
    }

    new ssm.StringParameter(this, "AppealsKBIdParam", {
      parameterName: `/${props.stackNameBase}/appeals-kb-id`,
      stringValue: this.knowledgeBase.attrKnowledgeBaseId,
    })
    new ssm.StringParameter(this, "AppealsKBRoleArnParam", {
      parameterName: `/${props.stackNameBase}/appeals/kb_role_arn`,
      stringValue: kbRole.roleArn,
    })

    new cdk.CfnOutput(this, "AppealsBucketName", { value: this.appealsBucket.bucketName })
    new cdk.CfnOutput(this, "AppealsKBDataBucketName", { value: kbDataBucket.bucketName })
    new cdk.CfnOutput(this, "AppealsKnowledgeBaseId", { value: this.knowledgeBase.attrKnowledgeBaseId })
  }
}
