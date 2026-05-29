#!/usr/bin/env node
import * as cdk from "aws-cdk-lib"
import { HealthcareAgentsMainStack } from "../lib/healthcare-agents-main-stack"
import { BackendStack } from "../lib/backend-stack"
import { SafetyAnalysisStack } from "../lib/safety-analysis-stack"
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

  // Note: Pattern-specific outputs (RuntimeArn, MemoryArn, etc.) are already
  // defined in the BackendStack itself, so we don't need to add them here
}

// Deploy the independent safety analysis stack
// This stack looks up DynamoDB tables via SSM parameters
// and can be deployed separately from the main stack
const safetyAnalysisStack = new SafetyAnalysisStack(app, `${props.stack_name_base}-safety-analysis`, {
  stackNameBase: props.stack_name_base,
  env: env,
})

// Add dependency: safety analysis only depends on hospital-safety-agent
// which creates the DynamoDB tables that safety-analysis replicates
const hospitalSafetyStack = backendStacks.find(stack =>
  stack.node.id.includes('hospital-safety-agent')
)
if (hospitalSafetyStack) {
  safetyAnalysisStack.addDependency(hospitalSafetyStack)
}

app.synth()
