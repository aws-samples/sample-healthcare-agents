#!/usr/bin/env node
// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import 'source-map-support/register';
import * as cdk from 'aws-cdk-lib';
import { EpicJwksStack } from '../lib/epic-jwks-stack';

const app = new cdk.App();

new EpicJwksStack(app, 'EpicJwksStack', {
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: process.env.CDK_DEFAULT_REGION || 'us-east-1'
  },
  description: 'Epic FHIR JWKS hosting infrastructure (S3 + CloudFront)'
});
