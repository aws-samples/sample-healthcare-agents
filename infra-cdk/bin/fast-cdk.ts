#!/usr/bin/env node
import * as cdk from "aws-cdk-lib"
import { HealthcareAgentsMainStack } from "../lib/healthcare-agents-main-stack"
import { BackendStack } from "../lib/backend-stack"
import { ConfigManager, AppConfig } from "../lib/utils/config-manager"

// Load configuration using ConfigManager
const configManager = new ConfigManager("config.yaml")

// Initial props consist of configuration parameters
const props = configManager.getProps()

const app = new cdk.App()

const env = {
  account: process.env.CDK_DEFAULT_ACCOUNT,
  region: process.env.CDK_DEFAULT_REGION
}

// Deploy the main stack with shared infrastructure (Amplify, Cognito)
const mainStack = new HealthcareAgentsMainStack(app, props.stack_name_base, {
  config: props,
  env: env,
})

// Get enabled patterns from configuration
const enabledPatterns = configManager.getEnabledPatterns()

console.log(`Deploying ${enabledPatterns.length} agent pattern(s):`)
enabledPatterns.forEach(p => console.log(`  - ${p.pattern} (${p.deployment_type})`))

// Deploy a separate backend stack for each enabled pattern
const backendStacks: BackendStack[] = []

for (const patternConfig of enabledPatterns) {
  // Create a unique stack ID for this pattern
  const patternStackId = `${props.stack_name_base}-${patternConfig.pattern}`

  // Create a modified config for this specific pattern
  const patternProps: AppConfig = {
    ...props,
    backend: {
      ...props.backend,
      pattern: patternConfig.pattern,
      deployment_type: patternConfig.deployment_type,
    }
  }

  console.log(`Creating backend stack: ${patternStackId}`)

  const backendStack = new BackendStack(app, patternStackId, {
    config: patternProps,
    userPoolId: mainStack.cognitoStack.userPoolId,
    userPoolClientId: mainStack.cognitoStack.userPoolClientId,
    userPoolDomain: mainStack.cognitoStack.userPoolDomain,
    frontendUrl: mainStack.amplifyHostingStack.amplifyUrl,
    sharedGateway: mainStack.sharedGateway,
    sharedGatewayRole: mainStack.sharedGatewayRole,
    machineClient: mainStack.machineClient,
    env: env,
  })

  // Backend stack depends on main stack (for Cognito, Amplify, and shared Gateway)
  backendStack.addDependency(mainStack)

  backendStacks.push(backendStack)
}

app.synth()
