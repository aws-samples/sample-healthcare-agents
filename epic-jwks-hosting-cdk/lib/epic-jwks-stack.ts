// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import * as cdk from 'aws-cdk-lib';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as s3deploy from 'aws-cdk-lib/aws-s3-deployment';
import * as cloudfront from 'aws-cdk-lib/aws-cloudfront';
import * as origins from 'aws-cdk-lib/aws-cloudfront-origins';
import { Construct } from 'constructs';
import * as path from 'path';

export class EpicJwksStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // S3 bucket to store JWKS file
    const jwksBucket = new s3.Bucket(this, 'JwksBucket', {
      bucketName: `epic-fhir-jwks-${this.account}`,
      encryption: s3.BucketEncryption.S3_MANAGED,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      removalPolicy: cdk.RemovalPolicy.RETAIN, // Keep bucket on stack deletion
      autoDeleteObjects: false,
      versioned: false,
      cors: [
        {
          allowedMethods: [s3.HttpMethods.GET, s3.HttpMethods.HEAD],
          allowedOrigins: ['*'],
          allowedHeaders: ['*'],
          maxAge: 3600,
        },
      ],
    });

    // CloudFront Origin Access Identity (OAI) for secure S3 access
    const originAccessIdentity = new cloudfront.OriginAccessIdentity(
      this,
      'JwksOAI',
      {
        comment: 'OAI for Epic FHIR JWKS bucket',
      }
    );

    // Grant CloudFront read access to S3 bucket
    jwksBucket.grantRead(originAccessIdentity);

    // CloudFront distribution
    const distribution = new cloudfront.Distribution(this, 'JwksDistribution', {
      defaultBehavior: {
        origin: origins.S3BucketOrigin.withOriginAccessIdentity(jwksBucket, {
          originAccessIdentity,
        }),
        viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.HTTPS_ONLY,
        allowedMethods: cloudfront.AllowedMethods.ALLOW_GET_HEAD,
        cachedMethods: cloudfront.CachedMethods.CACHE_GET_HEAD,
        cachePolicy: new cloudfront.CachePolicy(this, 'JwksCachePolicy', {
          cachePolicyName: `EpicJwksCachePolicy-${this.stackName}`,
          comment: 'Cache policy for Epic JWKS endpoint (29 hours default)',
          defaultTtl: cdk.Duration.hours(29), // Epic default cache time
          maxTtl: cdk.Duration.hours(29),
          minTtl: cdk.Duration.seconds(0),
          enableAcceptEncodingGzip: true,
          enableAcceptEncodingBrotli: true,
        }),
      },
      defaultRootObject: 'jwks.json',
      priceClass: cloudfront.PriceClass.PRICE_CLASS_100, // US, Canada, Europe
      comment: 'Epic FHIR JWKS endpoint',
      enabled: true,
    });

    // Deploy JWKS file to S3
    new s3deploy.BucketDeployment(this, 'DeployJwks', {
      sources: [s3deploy.Source.asset(path.join(__dirname, '../assets'))],
      destinationBucket: jwksBucket,
      distribution,
      distributionPaths: ['/*'], // Invalidate CloudFront cache on deployment
      cacheControl: [
        s3deploy.CacheControl.maxAge(cdk.Duration.hours(29)),
        s3deploy.CacheControl.mustRevalidate(),
      ],
    });

    // Stack Outputs
    new cdk.CfnOutput(this, 'JwksUrl', {
      value: `https://${distribution.distributionDomainName}/jwks.json`,
      description: 'Epic FHIR JWKS endpoint URL (register this in Epic app)',
      exportName: `${this.stackName}-JwksUrl`,
    });

    new cdk.CfnOutput(this, 'CloudFrontDomain', {
      value: distribution.distributionDomainName,
      description: 'CloudFront distribution domain',
      exportName: `${this.stackName}-CloudFrontDomain`,
    });

    new cdk.CfnOutput(this, 'S3BucketName', {
      value: jwksBucket.bucketName,
      description: 'S3 bucket storing JWKS file',
      exportName: `${this.stackName}-S3Bucket`,
    });
  }
}
