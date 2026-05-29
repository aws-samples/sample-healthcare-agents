import * as cdk from "aws-cdk-lib"
import * as cognito from "aws-cdk-lib/aws-cognito"
import * as iam from "aws-cdk-lib/aws-iam"
import * as ssm from "aws-cdk-lib/aws-ssm"
import * as secretsmanager from "aws-cdk-lib/aws-secretsmanager"
import * as dynamodb from "aws-cdk-lib/aws-dynamodb"
import * as apigateway from "aws-cdk-lib/aws-apigateway"
import * as logs from "aws-cdk-lib/aws-logs"
import * as s3 from "aws-cdk-lib/aws-s3"
import * as kms from "aws-cdk-lib/aws-kms"
import * as bedrock from "aws-cdk-lib/aws-bedrock"
import * as opensearchserverless from "aws-cdk-lib/aws-opensearchserverless"
import * as b2bi from "aws-cdk-lib/aws-b2bi"
import * as agentcore from "@aws-cdk/aws-bedrock-agentcore-alpha"
import * as bedrockagentcore from "aws-cdk-lib/aws-bedrockagentcore"
import { PythonFunction } from "@aws-cdk/aws-lambda-python-alpha"
import * as lambda from "aws-cdk-lib/aws-lambda"
import * as ecr_assets from "aws-cdk-lib/aws-ecr-assets"
import * as cr from "aws-cdk-lib/custom-resources"
import { Construct } from "constructs"
import { AppConfig } from "./utils/config-manager"
import { AgentCoreRole } from "./utils/agentcore-role"
import * as path from "path"
import * as fs from "fs"
import * as dotenv from "dotenv"
import { HospitalSafetyStack } from "./patterns/hospital-safety/hospital-safety-stack"
import { MedicalCodingStack } from "./patterns/medical-coding/medical-coding-stack"
import { ClaimsAssemblyStack } from "./patterns/claims-assembly/claims-assembly-stack"

// Load .env file for Langfuse configuration
dotenv.config({ path: path.join(__dirname, "../../.env") })

export interface BackendStackProps extends cdk.StackProps {
  config: AppConfig
  userPoolId: string
  userPoolClientId: string
  userPoolDomain: cognito.UserPoolDomain
  frontendUrl: string
  sharedGateway: bedrockagentcore.CfnGateway
  sharedGatewayRole: iam.Role
  machineClient: cognito.UserPoolClient
}

export class BackendStack extends cdk.Stack {
  public readonly userPoolId: string
  public readonly userPoolClientId: string
  public readonly userPoolDomain: cognito.UserPoolDomain
  public feedbackApiUrl: string
  public runtimeArn: string
  public memoryArn: string
  private agentName: cdk.CfnParameter
  private networkMode: cdk.CfnParameter
  private userPool: cognito.IUserPool
  private machineClient: cognito.UserPoolClient
  private agentRuntime: agentcore.Runtime
  public readonly dataEncryptionKey: kms.IKey
  public feedbackTable: dynamodb.Table
  private hospitalSafetyStack?: HospitalSafetyStack
  private medicalCodingStack?: MedicalCodingStack
  private claimsAssemblyStack?: ClaimsAssemblyStack

  // B2B Data Interchange resources
  private b2biProfileId?: string
  private b2biTransformerId?: string
  private b2biCapabilityId?: string

  // Getters for hospital safety tables
  public get eventsTable(): dynamodb.ITable | undefined {
    return this.hospitalSafetyStack?.eventsTable
  }

  public get analysisTable(): dynamodb.ITable | undefined {
    return this.hospitalSafetyStack?.analysisTable
  }

  constructor(scope: Construct, id: string, props: BackendStackProps) {
    const pattern = props.config.backend.pattern || 'unknown-pattern';
    const description = `Healthcare Agents Backend Stack - ${pattern} - AgentCore Runtime, Memory, Gateway, and Tools (v0.3.0) (uksb-v6dos0t5g8)`;
    super(scope, id, { ...props, description })

    // Store the Cognito values
    this.userPoolId = props.userPoolId
    this.userPoolClientId = props.userPoolClientId
    this.userPoolDomain = props.userPoolDomain

    // HIPAA Compliance: Create customer-managed KMS key for PHI/PII data encryption
    // This key is used for DynamoDB, SNS, S3 (agent code)

    this.dataEncryptionKey = new kms.Key(this, "DataEncryptionKey", {
      enableKeyRotation: true,
      description:
        "Customer-managed key for healthcare agents PHI/PII data encryption",
      alias: `${props.config.stack_name_base}-${pattern}-data-key`,
      removalPolicy: cdk.RemovalPolicy.RETAIN, // Never delete key with encrypted data
      pendingWindow: cdk.Duration.days(30), // 30-day recovery window
    })

    // Import the Cognito resources from the other stack
    this.userPool = cognito.UserPool.fromUserPoolId(
      this,
      "ImportedUserPoolForBackend",
      props.userPoolId
    )
    // then create the user pool client
    cognito.UserPoolClient.fromUserPoolClientId(
      this,
      "ImportedUserPoolClient",
      props.userPoolClientId
    )

    // Store shared resources from main stack
    this.machineClient = props.machineClient
    const gateway = props.sharedGateway
    const gatewayRole = props.sharedGatewayRole

    // DEPLOYMENT ORDER EXPLANATION:
    // 1. Cognito User Pool & Client (created in main stack CognitoStack)
    // 2. Machine Client & Resource Server (created in main stack for M2M auth)
    // 3. Shared Gateway (created ONCE in main stack, used by ALL patterns)
    // 4. Platform Feedback (created ONCE in main stack, used by ALL patterns)
    // 5. Knowledge Base (if medical-coding-agent - must be before runtime)
    // 6. AgentCore Runtime (per-pattern, references shared Gateway)
    // 7. Gateway Targets (tools registered to shared Gateway by each pattern)
    //
    // This order ensures shared resources are created first, then per-pattern resources

    // Create AgentCore Runtime resources
    this.createAgentCoreRuntime(props.config)

    // Create MCP Server target for hospital safety agent (after Runtime is created)
    // NOTE: This is pattern-specific and creates a Lambda wrapper for the Runtime
    // Common tools (HealthLake, Comprehend Medical) are created in main stack
    // TODO: Add hospital-safety-agent MCP target later
    // if (props.config.backend?.pattern === "hospital-safety-agent") {
    //   this.createHospitalSafetyMcpTarget(gateway, props.config)
    // }

    // Store runtime ARN in SSM for frontend stack
    this.createRuntimeSSMParameters(props.config)

    // Note: Cognito SSM parameters and Gateway URL are created in main stack (shared by all patterns)
    // Note: Feedback API is created in main stack (shared by all patterns)

    // Output shared Gateway information
    new cdk.CfnOutput(this, "GatewayId", {
      value: gateway.attrGatewayIdentifier,
      description: "Shared AgentCore Gateway ID (all patterns use this Gateway)",
    })

    new cdk.CfnOutput(this, "GatewayUrl", {
      value: gateway.attrGatewayUrl,
      description: "Shared Gateway URL",
    })

    // Note: Gateway URL SSM parameter is created in main stack (shared by all patterns)
  }

  private createAgentCoreRuntime(config: AppConfig): void {
    const pattern = config.backend?.pattern || "strands-single-agent"

    // Parameters - make agent name unique per pattern
    const prefix = config.stack_name_base.replace(/-/g, "_") + "_"
    const fullAgentName = pattern.split('-').map(word =>
      word.charAt(0).toUpperCase() + word.slice(1)
    ).join('') + 'Agent'
    // AgentCore runtime names must be <= 48 chars: truncate if needed
    const defaultAgentName = fullAgentName.substring(0, 48 - prefix.length)

    this.agentName = new cdk.CfnParameter(this, "AgentName", {
      type: "String",
      default: defaultAgentName,
      description: "Name for the agent runtime",
    })

    this.networkMode = new cdk.CfnParameter(this, "NetworkMode", {
      type: "String",
      default: "PUBLIC",
      description: "Network mode for AgentCore resources",
      allowedValues: ["PUBLIC", "PRIVATE"],
    })

    const stack = cdk.Stack.of(this)
    const deploymentType = config.backend.deployment_type

    // Create the agent runtime artifact based on deployment type
    let agentRuntimeArtifact: agentcore.AgentRuntimeArtifact
    let zipPackagerResource: cdk.CustomResource | undefined

    if (deploymentType === "zip" && (pattern === "claude-agent-sdk-single-agent" || pattern === "claude-agent-sdk-multi-agent")) {
      throw new Error(
        "claude-agent-sdk patterns require Docker deployment (deployment_type: docker) " +
        "because they need Node.js and the claude-code CLI installed at build time."
      )
    }

    if (deploymentType === "zip") {
      // ZIP DEPLOYMENT: Use Lambda to package and upload to S3 (no Docker required)
      const repoRoot = path.resolve(__dirname, "..", "..")
      const patternDir = path.join(repoRoot, "patterns", pattern)

      // Create S3 bucket for agent code with CMK encryption
      const agentCodeBucket = new s3.Bucket(this, "AgentCodeBucket", {
        removalPolicy: cdk.RemovalPolicy.DESTROY,
        autoDeleteObjects: true,
        versioned: true,
        blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
        encryptionKey: this.dataEncryptionKey,
        encryption: s3.BucketEncryption.KMS,
      })

      // Lambda to package agent code
      const packagerLambda = new lambda.Function(this, "ZipPackagerLambda", {
        runtime: lambda.Runtime.PYTHON_3_12,
        handler: "index.handler",
        code: lambda.Code.fromAsset(path.join(__dirname, "..", "lambdas", "zip-packager")),
        timeout: cdk.Duration.minutes(10),
        memorySize: 1024,
        ephemeralStorageSize: cdk.Size.gibibytes(2),
      })

      agentCodeBucket.grantReadWrite(packagerLambda)

      // Read agent code files and encode as base64
      const agentCode: Record<string, string> = {}
      
      // Read pattern .py files
      for (const file of fs.readdirSync(patternDir)) {
        if (file.endsWith(".py")) {
          const content = fs.readFileSync(path.join(patternDir, file))
          agentCode[file] = content.toString("base64")
        }
      }

      // Read shared modules (gateway/, tools/)
      for (const module of ["gateway", "tools"]) {
        const moduleDir = path.join(repoRoot, module)
        if (fs.existsSync(moduleDir)) {
          this.readDirRecursive(moduleDir, module, agentCode)
        }
      }

      // Read requirements
      const requirementsPath = path.join(patternDir, "requirements.txt")
      const requirements = fs.readFileSync(requirementsPath, "utf-8")
        .split("\n")
        .map(line => line.trim())
        .filter(line => line && !line.startsWith("#"))

      // Create hash for change detection
      // We use this to trigger update when content changes
      const contentHash = this.hashContent(JSON.stringify({ requirements, agentCode }))

      // Custom Resource to trigger packaging
      const provider = new cr.Provider(this, "ZipPackagerProvider", {
        onEventHandler: packagerLambda,
      })

      zipPackagerResource = new cdk.CustomResource(this, "ZipPackager", {
        serviceToken: provider.serviceToken,
        properties: {
          BucketName: agentCodeBucket.bucketName,
          ObjectKey: "deployment_package.zip",
          Requirements: requirements,
          AgentCode: agentCode,
          ContentHash: contentHash,
        },
      })

      // Store bucket name in SSM for updates
      new ssm.StringParameter(this, "AgentCodeBucketNameParam", {
        parameterName: `/${config.stack_name_base}/agent-code-bucket`,
        stringValue: agentCodeBucket.bucketName,
        description: "S3 bucket for agent code deployment packages",
      })

      agentRuntimeArtifact = agentcore.AgentRuntimeArtifact.fromS3(
        {
          bucketName: agentCodeBucket.bucketName,
          objectKey: "deployment_package.zip",
        },
        agentcore.AgentCoreRuntime.PYTHON_3_12,
        ["opentelemetry-instrument", "basic_agent.py"]
      )
    } else {
      // DOCKER DEPLOYMENT: Use container-based deployment
      agentRuntimeArtifact = agentcore.AgentRuntimeArtifact.fromAsset(
        path.resolve(__dirname, "..", ".."),
        {
          platform: ecr_assets.Platform.LINUX_ARM64,
          file: `patterns/${pattern}/Dockerfile`,
        }
      )
    }

    // Configure network mode
    const networkConfiguration =
      this.networkMode.valueAsString === "PRIVATE"
        ? undefined // For private mode, you would need to configure VPC settings
        : agentcore.RuntimeNetworkConfiguration.usingPublicNetwork()

    // Configure JWT authorizer with Cognito (accept both user and machine client IDs)
    const authorizerConfiguration = agentcore.RuntimeAuthorizerConfiguration.usingJWT(
      `https://cognito-idp.${stack.region}.amazonaws.com/${this.userPoolId}/.well-known/openid-configuration`,
      [this.userPoolClientId, this.machineClient.userPoolClientId]
    )

    // Create AgentCore execution role
    const agentRole = new AgentCoreRole(this, "AgentCoreRole")

    // Create Hospital Safety Infrastructure (if hospital-safety-agent pattern is used)
    if (pattern === "hospital-safety-agent") {
      this.hospitalSafetyStack = new HospitalSafetyStack(this, "HospitalSafety", {
        stackNameBase: config.stack_name_base,
        safetyOfficerEmail: "safety@example.com",
        physicianEmail: "physician@example.com",
        agentCoreRoleArn: agentRole.roleArn,
        dataEncryptionKey: this.dataEncryptionKey,
      })
    }

    // Create Medical Coding Infrastructure (if medical-coding-agent pattern is used)
    if (pattern === "medical-coding-agent") {
      this.medicalCodingStack = new MedicalCodingStack(this, "MedicalCoding", {
        stackNameBase: config.stack_name_base,
        agentCoreRoleArn: agentRole.roleArn,
        dataEncryptionKey: this.dataEncryptionKey,
      })
    }

    // Create Claims Assembly Infrastructure (if claims-assembly-agent pattern is used)
    if (pattern === "claims-assembly-agent") {
      this.claimsAssemblyStack = new ClaimsAssemblyStack(this, "ClaimsAssembly", {
        stackNameBase: config.stack_name_base,
        agentCoreRoleArn: agentRole.roleArn,
        dataEncryptionKey: this.dataEncryptionKey,
      })
    }

    // Create memory resource with short-term memory (conversation history) as default
    // To enable long-term strategies (summaries, preferences, facts), see docs/MEMORY_INTEGRATION.md
    // Note: AgentCore Memory encryption is managed by the service (cannot specify custom KMS key)
    const memory = new cdk.CfnResource(this, "AgentMemory", {
      type: "AWS::BedrockAgentCore::Memory",
      properties: {
        Name: cdk.Names.uniqueResourceName(this, { maxLength: 48 }),
        EventExpiryDuration: 30,
        Description: `Short-term memory for ${config.stack_name_base} agent`,
        MemoryStrategies: [], // Empty array = short-term only (conversation history)
        MemoryExecutionRoleArn: agentRole.roleArn,
        Tags: {
          Name: `${config.stack_name_base}_Memory`,
          ManagedBy: "CDK",
        },
      },
    })
    const memoryId = memory.getAtt("MemoryId").toString()
    const memoryArn = memory.getAtt("MemoryArn").toString()

    // Store the memory ARN for access from main stack
    this.memoryArn = memoryArn

    // Add memory-specific permissions to agent role
    agentRole.addToPolicy(
      new iam.PolicyStatement({
        sid: "MemoryResourceAccess",
        effect: iam.Effect.ALLOW,
        actions: [
          "bedrock-agentcore:CreateEvent",
          "bedrock-agentcore:GetEvent",
          "bedrock-agentcore:ListEvents",
          "bedrock-agentcore:RetrieveMemoryRecords", // Only needed for long-term strategies
        ],
        resources: [memoryArn],
      })
    )

    // Add SSM permissions for Gateway URL lookup
    agentRole.addToPolicy(
      new iam.PolicyStatement({
        sid: "SSMParameterAccess",
        effect: iam.Effect.ALLOW,
        actions: ["ssm:GetParameter", "ssm:GetParameters"],
        resources: [
          `arn:aws:ssm:${this.region}:${this.account}:parameter/${config.stack_name_base}/*`,
        ],
      })
    )

    // Add Bedrock Guardrail permissions for PHI masking in observability
    agentRole.addToPolicy(
      new iam.PolicyStatement({
        sid: "BedrockGuardrailAccess",
        effect: iam.Effect.ALLOW,
        actions: ["bedrock:ApplyGuardrail"],
        resources: [
          `arn:aws:bedrock:${this.region}:${this.account}:guardrail/*`,
        ],
      })
    )

    // Add Code Interpreter permissions
    agentRole.addToPolicy(
      new iam.PolicyStatement({
        sid: "CodeInterpreterAccess",
        effect: iam.Effect.ALLOW,
        actions: [
          "bedrock-agentcore:StartCodeInterpreterSession",
          "bedrock-agentcore:StopCodeInterpreterSession",
          "bedrock-agentcore:InvokeCodeInterpreter",
        ],
        resources: [`arn:aws:bedrock-agentcore:${this.region}:aws:code-interpreter/*`],
      })
    )

    // Note: Knowledge Base permissions are now granted by pattern-specific nested stacks
    // (MedicalCodingStack, ClaimsAssemblyStack) which create KB infrastructure

    // HIPAA Compliance: Grant KMS permissions for data encryption/decryption
    this.dataEncryptionKey.grantEncryptDecrypt(agentRole)

    // Create Bedrock Prompt Management prompts for supported agent patterns and grant IAM access
    const promptManagedPatterns = ["medical-coding-agent", "claims-assembly-agent", "claims-submission-agent"]
    if (promptManagedPatterns.includes(pattern)) {
      this.createManagedPrompts(config, agentRole, pattern)
    }

    // Environment variables for the runtime
    const envVars: { [key: string]: string } = {
      AWS_REGION: stack.region,
      AWS_DEFAULT_REGION: stack.region,
      MEMORY_ID: memoryId,
      STACK_NAME: config.stack_name_base, // Required for agent to find SSM parameters
      MODEL_ID: "us.anthropic.claude-sonnet-4-5-20250929-v1:0", // Bedrock model for agents
    }

    // For patterns using Bedrock Prompt Management, pass the SSM path so the agent
    // can look up the versioned prompt ARN at runtime
    if (promptManagedPatterns.includes(pattern)) {
      envVars.SYSTEM_PROMPT_SSM_PATH = `/${config.stack_name_base}/prompts/${pattern}`
    }

    // Add Knowledge Base ID if medical-coding-agent pattern
    // KB must be created manually after the nested stack creates the collection
    if (config.backend?.pattern === "medical-coding-agent") {
      const manualKbId = this.node.tryGetContext("knowledgeBaseId")
      if (manualKbId) {
        envVars.KNOWLEDGE_BASE_ID = manualKbId
      } else {
        console.log("[CDK] KNOWLEDGE_BASE_ID not provided. Create KB manually and pass via context: -c knowledgeBaseId=<kb-id>")
      }
    }

    // Add Validation KB ID if claims-assembly-agent pattern
    // KB must be created manually after the nested stack creates the collection
    if (config.backend?.pattern === "claims-assembly-agent") {
      const manualValidationKbId = this.node.tryGetContext("validationKbId")
      if (manualValidationKbId) {
        envVars.VALIDATION_KB_ID = manualValidationKbId
      } else {
        console.log("[CDK] VALIDATION_KB_ID not provided. Create validation KB manually and pass via context: -c validationKbId=<kb-id>")
      }
    }

    // HIPAA Compliance: Langfuse secret for observability
    // Shared across all patterns - import existing secret instead of creating new one
    const langfuseSecretKey = process.env.LANGFUSE_SECRET_KEY || ""
    const langfusePublicKey = process.env.LANGFUSE_PUBLIC_KEY || ""
    const langfuseBaseUrl = process.env.LANGFUSE_BASE_URL || ""

    // Import the existing shared Langfuse secret (created by first pattern or main stack)
    const langfuseSecret = secretsmanager.Secret.fromSecretNameV2(
      this,
      "LangfuseSecret",
      `/${config.stack_name_base}/langfuse/credentials`
    )

    // Grant agent role read access to Langfuse secret
    langfuseSecret.grantRead(agentRole)

    // Add Langfuse observability configuration
    if (langfuseSecretKey && langfusePublicKey && langfuseBaseUrl) {
      // Add secret ARN and OTEL endpoint to environment variables
      // Auth header will be constructed at runtime from Secrets Manager
      const otelEndpoint = `${langfuseBaseUrl}/api/public/otel`

      envVars.OTEL_EXPORTER_OTLP_ENDPOINT = otelEndpoint
      envVars.LANGFUSE_SECRET_ARN = langfuseSecret.secretArn
      envVars.LANGFUSE_TRACING_ENVIRONMENT = process.env.DEPLOY_ENV ?? "dev"
      envVars.DISABLE_ADOT_OBSERVABILITY = "true"  // Disable AgentCore default observability

      console.log(`[CDK] Langfuse observability configured with Secrets Manager: ${otelEndpoint}`)
    } else {
      console.log("[CDK] Langfuse credentials not found in .env - secret created but empty")
    }

    // Add hospital safety environment variables if the pattern is hospital-safety-agent
    if (this.hospitalSafetyStack) {
      envVars.EVENTS_TABLE_NAME = this.hospitalSafetyStack.eventsTable.tableName
      envVars.ANALYSIS_TABLE_NAME = this.hospitalSafetyStack.analysisTable.tableName
      envVars.ALERT_SNS_TOPIC_ARN = this.hospitalSafetyStack.alertTopic.topicArn

      // Add email notification recipients from environment or use defaults
      envVars.PHYSICIAN_EMAIL = process.env.PHYSICIAN_EMAIL || "physician@example.com"
      envVars.SAFETY_OFFICER_EMAIL = process.env.SAFETY_OFFICER_EMAIL || "safety@example.com"
      envVars.DISABLE_ALERTS = process.env.DISABLE_ALERTS || "true"

      // Use Claude Sonnet 4.6 for hospital safety agent
      envVars.MODEL_ID = "us.anthropic.claude-sonnet-4-6"

      // Grant Comprehend Medical InferRxNorm for drug name normalization
      agentRole.addToPolicy(
        new iam.PolicyStatement({
          sid: "ComprehendMedicalRxNorm",
          effect: iam.Effect.ALLOW,
          actions: ["comprehendmedical:InferRxNorm"],
          resources: ["*"],
        })
      )
    }

    // Add claude-agent-sdk specific environment variable
    if (pattern === "claude-agent-sdk-single-agent" || pattern === "claude-agent-sdk-multi-agent") {
      envVars["CLAUDE_CODE_USE_BEDROCK"] = "1"
    }

    // Create the runtime using L2 construct
    // Use shorter runtime name to stay within 48 character limit (pattern: [a-zA-Z][a-zA-Z0-9_]{0,47})
    const runtimeName = `${pattern.replace(/-/g, "_")}_runtime`.substring(0, 48)
    this.agentRuntime = new agentcore.Runtime(this, "Runtime", {
      runtimeName: runtimeName,
      agentRuntimeArtifact: agentRuntimeArtifact,
      executionRole: agentRole,
      networkConfiguration: networkConfiguration,
      protocolConfiguration: agentcore.ProtocolType.HTTP,
      environmentVariables: envVars,
      authorizerConfiguration: authorizerConfiguration,
      description: `${pattern} agent runtime for ${config.stack_name_base}`,
    })

    // AGUI protocol override — CloudFormation doesn't support AGUI enum yet
    // (only MCP | HTTP | A2A). Runtime deploys as HTTP, which also works properly.
    // if (pattern.startsWith("agui-")) {
    //   const cfnRuntime = this.agentRuntime.node.defaultChild as cdk.CfnResource
    //   cfnRuntime.addPropertyOverride("ProtocolConfiguration", "AGUI")
    // }

    // Make sure that ZIP is uploaded before Runtime is created
    if (zipPackagerResource) {
      this.agentRuntime.node.addDependency(zipPackagerResource)
    }

    // Store the runtime ARN
    this.runtimeArn = this.agentRuntime.agentRuntimeArn

    // Outputs
    new cdk.CfnOutput(this, "AgentRuntimeId", {
      description: "ID of the created agent runtime",
      value: this.agentRuntime.agentRuntimeId,
    })

    new cdk.CfnOutput(this, "AgentRuntimeArn", {
      description: "ARN of the created agent runtime",
      value: this.agentRuntime.agentRuntimeArn,
      exportName: `${config.stack_name_base}-${config.backend?.pattern}-AgentRuntimeArn`,
    })

    new cdk.CfnOutput(this, "AgentRoleArn", {
      description: "ARN of the agent execution role",
      value: agentRole.roleArn,
    })

    // Memory ARN output
    new cdk.CfnOutput(this, "MemoryArn", {
      description: "ARN of the agent memory resource",
      value: memoryArn,
    })
  }

  private createRuntimeSSMParameters(config: AppConfig): void {
    // Store runtime ARN in SSM for frontend stack
    const pattern = config.backend?.pattern || "strands-single-agent"
    new ssm.StringParameter(this, "RuntimeArnParam", {
      parameterName: `/${config.stack_name_base}/${pattern}/runtime-arn`,
      stringValue: this.runtimeArn,
    })
  }

  // Note: createCognitoSSMParameters moved to main stack (shared by all patterns)

  // Creates a DynamoDB table for storing user feedback.
  private createFeedbackTable(config: AppConfig): dynamodb.Table {
    this.feedbackTable = new dynamodb.Table(this, "FeedbackTable", {
      tableName: `${config.stack_name_base}-feedback`,
      partitionKey: {
        name: "feedbackId",
        type: dynamodb.AttributeType.STRING,
      },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      pointInTimeRecoverySpecification: {
        pointInTimeRecoveryEnabled: true,
      },
      encryption: dynamodb.TableEncryption.CUSTOMER_MANAGED,
      encryptionKey: this.dataEncryptionKey,
      stream: dynamodb.StreamViewType.NEW_IMAGE, // Enable streams for Aurora replication
    })

    // Add GSI for querying by feedbackType with timestamp sorting
    this.feedbackTable.addGlobalSecondaryIndex({
      indexName: "feedbackType-timestamp-index",
      partitionKey: {
        name: "feedbackType",
        type: dynamodb.AttributeType.STRING,
      },
      sortKey: {
        name: "timestamp",
        type: dynamodb.AttributeType.NUMBER,
      },
      projectionType: dynamodb.ProjectionType.ALL,
    })

    // Store feedback table name in SSM for Lambda access
    new ssm.StringParameter(this, "FeedbackTableNameParam", {
      parameterName: `/${config.stack_name_base}/feedback_table_name`,
      stringValue: this.feedbackTable.tableName,
      description: "DynamoDB table name for user feedback",
    })

    // Store feedback table ARN in SSM for safety-analysis stack lookup
    new ssm.StringParameter(this, "FeedbackTableArnParam", {
      parameterName: `/${config.stack_name_base}/feedback_table_arn`,
      stringValue: this.feedbackTable.tableArn,
      description: "DynamoDB table ARN for user feedback",
    })

    // Store feedback table stream ARN for replication
    new ssm.StringParameter(this, "FeedbackTableStreamArnParam", {
      parameterName: `/${config.stack_name_base}/feedback_table_stream_arn`,
      stringValue: this.feedbackTable.tableStreamArn!,
      description: "DynamoDB table stream ARN for user feedback",
    })

    return this.feedbackTable
  }

  /**
   * Creates S3 bucket for medical codes knowledge base data.
   */
  private createKnowledgeBaseBucket(config: AppConfig): s3.Bucket {
    const bucket = new s3.Bucket(this, "MedicalCodesKBBucket", {
      bucketName: `${config.stack_name_base}-medical-codes-kb-${cdk.Aws.ACCOUNT_ID}`,
      encryption: s3.BucketEncryption.S3_MANAGED,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      removalPolicy: cdk.RemovalPolicy.RETAIN,
      versioned: true,
    })

    new cdk.CfnOutput(this, "KnowledgeBaseBucket", {
      value: bucket.bucketName,
      description: "S3 bucket for medical codes knowledge base",
    })

    return bucket
  }

  /**
   * Creates Bedrock Knowledge Base for medical codes using S3 Vectors as the vector store.
   * S3 Vectors requires no OpenSearch infrastructure and has no policy propagation delays.
   */
  private createMedicalCodesKnowledgeBase(
    config: AppConfig,
    bucket: s3.Bucket,
  ): bedrock.CfnKnowledgeBase {
    const s3vectors = require("aws-cdk-lib/aws-s3vectors")

    // Create S3 vector bucket (stores the embeddings)
    const vectorBucket = new s3vectors.CfnVectorBucket(this, "KBVectorBucket", {
      vectorBucketName: `${config.stack_name_base}-kb-vectors`,
    })

    // Create vector index inside the bucket.
    // Titan Embed Text v2 produces 1024-dimensional float32 vectors.
    const vectorIndex = new s3vectors.CfnIndex(this, "KBVectorIndex", {
      vectorBucketArn: vectorBucket.getAtt("VectorBucketArn").toString(),
      indexName: "medical-codes-index",
      dataType: "float32",
      dimension: 1024,
      distanceMetric: "cosine",
    })
    vectorIndex.addDependency(vectorBucket)

    // IAM role for the Knowledge Base
    const kbRole = new iam.Role(this, "KnowledgeBaseRole", {
      assumedBy: new iam.ServicePrincipal("bedrock.amazonaws.com"),
      description: "Role for Bedrock Knowledge Base to access S3 and S3 Vectors",
    })

    // Grant read access to the S3 data source bucket
    bucket.grantRead(kbRole)

    // Grant S3 Vectors permissions for embedding storage and retrieval
    kbRole.addToPolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: [
          "s3vectors:GetIndex",
          "s3vectors:PutVectors",
          "s3vectors:GetVectors",
          "s3vectors:DeleteVectors",
          "s3vectors:QueryVectors",
          "s3vectors:ListVectors",
        ],
        resources: [
          vectorBucket.getAtt("VectorBucketArn").toString(),
          `${vectorBucket.getAtt("VectorBucketArn").toString()}/index/*`,
        ],
      })
    )

    // Grant Bedrock model access for embedding generation
    kbRole.addToPolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: ["bedrock:InvokeModel"],
        resources: [
          `arn:aws:bedrock:${this.region}::foundation-model/amazon.titan-embed-text-v2:0`,
        ],
      })
    )

    const knowledgeBase = new bedrock.CfnKnowledgeBase(this, "MedicalCodesKB", {
      name: `${config.stack_name_base}-medical-codes`,
      roleArn: kbRole.roleArn,
      knowledgeBaseConfiguration: {
        type: "VECTOR",
        vectorKnowledgeBaseConfiguration: {
          embeddingModelArn: `arn:aws:bedrock:${this.region}::foundation-model/amazon.titan-embed-text-v2:0`,
        },
      },
      storageConfiguration: {
        type: "S3_VECTORS",
        s3VectorsConfiguration: {
          vectorBucketArn: vectorBucket.getAtt("VectorBucketArn").toString(),
          indexArn: vectorIndex.getAtt("IndexArn").toString(),
          indexName: "medical-codes-index",
        },
      },
    })
    knowledgeBase.addDependency(vectorIndex)

    new bedrock.CfnDataSource(this, "MedicalCodesDataSource", {
      knowledgeBaseId: knowledgeBase.attrKnowledgeBaseId,
      name: "medical-codes-s3",
      dataSourceConfiguration: {
        type: "S3",
        s3Configuration: {
          bucketArn: bucket.bucketArn,
        },
      },
    })

    new cdk.CfnOutput(this, "KnowledgeBaseId", {
      value: knowledgeBase.attrKnowledgeBaseId,
      description: "Medical codes knowledge base ID",
    })

    new ssm.StringParameter(this, "KnowledgeBaseIdParam", {
      parameterName: `/${config.stack_name_base}/knowledge_base_id`,
      stringValue: knowledgeBase.attrKnowledgeBaseId,
      description: "Knowledge Base ID for medical coding agent",
    })

    return knowledgeBase
  }

  /**
   * Creates an API Gateway with Lambda integration for the feedback endpoint.
   * This is an EXAMPLE implementation demonstrating best practices for API Gateway + Lambda.
   *
   * API Contract - POST /feedback
   * Authorization: Bearer <cognito-access-token> (required)
   *
   * Request Body:
   *   sessionId: string (required, max 100 chars, alphanumeric with -_) - Conversation session ID
   *   message: string (required, max 5000 chars) - Agent's response being rated
   *   feedbackType: "positive" | "negative" (required) - User's rating
   *   comment: string (optional, max 5000 chars) - User's explanation for rating
   *
   * Success Response (200):
   *   { success: true, feedbackId: string }
   *
   * Error Responses:
   *   400: { error: string } - Validation failure (missing fields, invalid format)
   *   401: { error: "Unauthorized" } - Invalid/missing JWT token
   *   500: { error: "Internal server error" } - DynamoDB or processing error
   *
   * Implementation: infra-cdk/lambdas/feedback/index.py
   */
  private createFeedbackApi(
    config: AppConfig,
    frontendUrl: string,
    feedbackTable: dynamodb.Table
  ): void {
    // Create Lambda function for feedback using Python
    const feedbackLambda = new PythonFunction(this, "FeedbackLambda", {
      functionName: `${config.stack_name_base}-feedback`,
      runtime: lambda.Runtime.PYTHON_3_12,
      entry: path.join(__dirname, "..", "lambdas", "feedback"),
      handler: "handler",
      environment: {
        TABLE_NAME: feedbackTable.tableName,
        CORS_ALLOWED_ORIGINS: `${frontendUrl},http://localhost:3000`,
      },
      timeout: cdk.Duration.seconds(30),
      layers: [
        lambda.LayerVersion.fromLayerVersionArn(
          this,
          "PowertoolsLayer",
          `arn:aws:lambda:${
            cdk.Stack.of(this).region
          }:017000801446:layer:AWSLambdaPowertoolsPythonV3-python313-arm64:18`
        ),
      ],
      logGroup: new logs.LogGroup(this, "FeedbackLambdaLogGroup", {
        logGroupName: `/aws/lambda/${config.stack_name_base}-feedback`,
        retention: logs.RetentionDays.ONE_WEEK,
        removalPolicy: cdk.RemovalPolicy.DESTROY,
      }),
    })

    // Grant Lambda permissions to write to DynamoDB
    feedbackTable.grantWriteData(feedbackLambda)

    /*
     * CORS TODO: Wildcard (*) used because Backend deploys before Frontend in nested stack order.
     * For Lambda proxy integrations, the Lambda's ALLOWED_ORIGINS env var is the primary CORS control.
     * API Gateway defaultCorsPreflightOptions below only handles OPTIONS preflight requests.
     * See detailed explanation and fix options in: infra-cdk/lambdas/feedback/index.py
     */
    const api = new apigateway.RestApi(this, "FeedbackApi", {
      restApiName: `${config.stack_name_base}-api`,
      description: "API for user feedback and future endpoints",
      defaultCorsPreflightOptions: {
        allowOrigins: [frontendUrl, "http://localhost:3000"],
        allowMethods: ["POST", "OPTIONS"],
        allowHeaders: ["Content-Type", "Authorization"],
      },
      deployOptions: {
        stageName: "prod",
        throttlingRateLimit: 100,
        throttlingBurstLimit: 200,
        cachingEnabled: true,
        cacheDataEncrypted: true,
        cacheClusterEnabled: true,
        cacheClusterSize: "0.5",
        cacheTtl: cdk.Duration.minutes(5),
        loggingLevel: apigateway.MethodLoggingLevel.INFO,
        dataTraceEnabled: true,
        metricsEnabled: true,
        accessLogDestination: new apigateway.LogGroupLogDestination(
          new logs.LogGroup(this, "FeedbackApiAccessLogGroup", {
            logGroupName: `/aws/apigateway/${config.stack_name_base}-api-access`,
            retention: logs.RetentionDays.ONE_WEEK,
            removalPolicy: cdk.RemovalPolicy.DESTROY,
          })
        ),
        accessLogFormat: apigateway.AccessLogFormat.jsonWithStandardFields(),
        tracingEnabled: true,
      },
    })

    // Add request validator for API security
    const requestValidator = new apigateway.RequestValidator(this, "FeedbackApiRequestValidator", {
      restApi: api,
      requestValidatorName: `${config.stack_name_base}-request-validator`,
      validateRequestBody: true,
      validateRequestParameters: true,
    })

    // Create Cognito authorizer
    const authorizer = new apigateway.CognitoUserPoolsAuthorizer(this, "FeedbackApiAuthorizer", {
      cognitoUserPools: [this.userPool],
      identitySource: "method.request.header.Authorization",
      authorizerName: `${config.stack_name_base}-authorizer`,
    })

    // Create /feedback resource and POST method
    const feedbackResource = api.root.addResource("feedback")
    feedbackResource.addMethod("POST", new apigateway.LambdaIntegration(feedbackLambda), {
      authorizer,
      authorizationType: apigateway.AuthorizationType.COGNITO,
      requestValidator: requestValidator,
    })

    // Store the API URL for access from main stack
    this.feedbackApiUrl = api.url

    // Store API URL in SSM for frontend
    new ssm.StringParameter(this, "FeedbackApiUrlParam", {
      parameterName: `/${config.stack_name_base}/feedback-api-url`,
      stringValue: api.url,
      description: "Feedback API Gateway URL",
    })
  }

  private createAgentCoreGateway(config: AppConfig): {
    gateway: bedrockagentcore.CfnGateway
    gatewayRole: iam.Role
  } {
    // Create sample tool Lambda
    const toolLambda = new lambda.Function(this, "SampleToolLambda", {
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: "sample_tool_lambda.handler",
      code: lambda.Code.fromAsset(path.join(__dirname, "../../gateway/tools/sample_tool")),
      timeout: cdk.Duration.seconds(30),
      logGroup: new logs.LogGroup(this, "SampleToolLambdaLogGroup", {
        logGroupName: `/aws/lambda/${config.stack_name_base}-sample-tool`,
        retention: logs.RetentionDays.ONE_WEEK,
        removalPolicy: cdk.RemovalPolicy.DESTROY,
      }),
    })

    // Create comprehensive IAM role for gateway
    const gatewayRole = new iam.Role(this, "GatewayRole", {
      assumedBy: new iam.ServicePrincipal("bedrock-agentcore.amazonaws.com"),
      description: "Role for AgentCore Gateway with comprehensive permissions",
    })

    // Lambda invoke permission
    toolLambda.grantInvoke(gatewayRole)

    // AgentCore Runtime invoke permissions (for MCP Server targets)
    gatewayRole.addToPolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: ["bedrock-agentcore:InvokeRuntime"],
        resources: [`arn:aws:bedrock-agentcore:${this.region}:${this.account}:runtime/*`],
      })
    )

    // Bedrock permissions (region-agnostic)
    gatewayRole.addToPolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
        resources: [
          "arn:aws:bedrock:*::foundation-model/*",
          `arn:aws:bedrock:*:${this.account}:inference-profile/*`,
        ],
      })
    )

    // SSM parameter access
    gatewayRole.addToPolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: ["ssm:GetParameter", "ssm:GetParameters"],
        resources: [
          `arn:aws:ssm:${this.region}:${this.account}:parameter/${config.stack_name_base}/*`,
        ],
      })
    )

    // Cognito permissions
    gatewayRole.addToPolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: ["cognito-idp:DescribeUserPoolClient", "cognito-idp:InitiateAuth"],
        resources: [this.userPool.userPoolArn],
      })
    )

    // CloudWatch Logs
    gatewayRole.addToPolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
        resources: [
          `arn:aws:logs:${this.region}:${this.account}:log-group:/aws/bedrock-agentcore/*`,
        ],
      })
    )

    // Load tool specification from JSON file
    const toolSpecPath = path.join(__dirname, "../../gateway/tools/sample_tool/tool_spec.json")
    const apiSpec = JSON.parse(require("fs").readFileSync(toolSpecPath, "utf8"))

    // Cognito OAuth2 configuration for gateway
    const cognitoIssuer = `https://cognito-idp.${this.region}.amazonaws.com/${this.userPool.userPoolId}`
    const cognitoDiscoveryUrl = `${cognitoIssuer}/.well-known/openid-configuration`

    // Create Gateway using L1 construct (CfnGateway)
    // This replaces the Custom Resource approach with native CloudFormation support
    const pattern = config.backend?.pattern || "default"
    const gateway = new bedrockagentcore.CfnGateway(this, "AgentCoreGateway", {
      name: `${config.stack_name_base}-${pattern}-gateway`,
      roleArn: gatewayRole.roleArn,
      protocolType: "MCP",
      protocolConfiguration: {
        mcp: {
          supportedVersions: ["2025-03-26"],
          // Optional: Enable semantic search for tools
          // searchType: "SEMANTIC",
        },
      },
      authorizerType: "CUSTOM_JWT",
      authorizerConfiguration: {
        customJwtAuthorizer: {
          allowedClients: [this.machineClient.userPoolClientId],
          discoveryUrl: cognitoDiscoveryUrl,
        },
      },
      description: "AgentCore Gateway with MCP protocol and JWT authentication",
    })

    // Create Gateway Target using L1 construct (CfnGatewayTarget)
    const gatewayTarget = new bedrockagentcore.CfnGatewayTarget(this, "GatewayTarget", {
      gatewayIdentifier: gateway.attrGatewayIdentifier,
      name: "sample-tool-target",
      description: "Sample tool Lambda target",
      targetConfiguration: {
        mcp: {
          lambda: {
            lambdaArn: toolLambda.functionArn,
            toolSchema: {
              inlinePayload: apiSpec,
            },
          },
        },
      },
      credentialProviderConfigurations: [
        {
          credentialProviderType: "GATEWAY_IAM_ROLE",
        },
      ],
    })

    // Ensure proper creation order
    gatewayTarget.addDependency(gateway)
    gateway.node.addDependency(toolLambda)
    gateway.node.addDependency(this.machineClient)
    gateway.node.addDependency(gatewayRole)

    // Store Gateway URL in SSM for runtime access
    new ssm.StringParameter(this, "GatewayUrlParam", {
      parameterName: `/${config.stack_name_base}/gateway_url`,
      stringValue: gateway.attrGatewayUrl,
      description: "AgentCore Gateway URL",
    })

    // Output gateway information
    new cdk.CfnOutput(this, "GatewayId", {
      value: gateway.attrGatewayIdentifier,
      description: "AgentCore Gateway ID",
    })

    new cdk.CfnOutput(this, "GatewayUrl", {
      value: gateway.attrGatewayUrl,
      description: "AgentCore Gateway URL",
    })

    new cdk.CfnOutput(this, "GatewayArn", {
      value: gateway.attrGatewayArn,
      description: "AgentCore Gateway ARN",
    })

    new cdk.CfnOutput(this, "GatewayTargetId", {
      value: gatewayTarget.ref,
      description: "AgentCore Gateway Target ID",
    })

    new cdk.CfnOutput(this, "ToolLambdaArn", {
      description: "ARN of the sample tool Lambda",
      value: toolLambda.functionArn,
    })

    return { gateway, gatewayRole }
  }

  /**
   * Creates Comprehend Medical Lambda target for AgentCore Gateway.
   */
  private createComprehendMedicalTarget(
    config: AppConfig,
    gateway: bedrockagentcore.CfnGateway,
    gatewayRole: iam.Role,
  ): void {
    // Create Lambda function
    const comprehendLambda = new lambda.Function(this, "ComprehendMedicalLambda", {
      functionName: `${config.stack_name_base}-comprehend-medical`,
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: "lambda_handler.lambda_handler",
      code: lambda.Code.fromAsset(
        path.join(__dirname, "../../gateway/tools/comprehend_medical"),
      ),
      timeout: cdk.Duration.seconds(30),
      memorySize: 512,
      environment: {
        LOG_LEVEL: "INFO",
      },
    })

    // Grant Comprehend Medical permissions
    comprehendLambda.addToRolePolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: ["comprehendmedical:DetectEntitiesV2", "comprehendmedical:DetectPHI"],
        resources: ["*"],
      }),
    )

    // Define tool schemas as ToolDefinitionProperty objects
    const toolSchemas = [
      {
        name: "extract_medical_entities",
        description:
          "Extract medical entities (medications, conditions, procedures, anatomy) from clinical text using AWS Comprehend Medical",
        inputSchema: {
          type: "object",
          properties: {
            text: {
              type: "string",
              description: "Clinical text to analyze for medical entities",
            },
          },
          required: ["text"],
        },
      },
      {
        name: "detect_phi",
        description: "Detect Protected Health Information (PHI) in clinical text",
        inputSchema: {
          type: "object",
          properties: {
            text: {
              type: "string",
              description: "Text to analyze for PHI",
            },
          },
          required: ["text"],
        },
      },
    ]

    // Create Gateway target
    new bedrockagentcore.CfnGatewayTarget(this, "ComprehendMedicalTarget", {
      gatewayIdentifier: gateway.attrGatewayIdentifier,
      name: "comprehend-medical-target",
      description: "Comprehend Medical tools for entity extraction and PHI detection",
      targetConfiguration: {
        mcp: {
          lambda: {
            lambdaArn: comprehendLambda.functionArn,
            toolSchema: {
              inlinePayload: toolSchemas as any,
            },
          },
        },
      },
      credentialProviderConfigurations: [
        {
          credentialProviderType: "GATEWAY_IAM_ROLE",
        },
      ],
    })

    // Grant Gateway role permission to invoke Lambda
    comprehendLambda.grantInvoke(gatewayRole)
  }

  private createHospitalSafetyMcpTarget(
    gateway: bedrockagentcore.CfnGateway,
    config: AppConfig
  ): void {

    // Create Lambda wrapper for Hospital Safety Agent with dependencies
    const safetyAgentLambda = new PythonFunction(this, "HospitalSafetyAgentLambda", {
      functionName: `${config.stack_name_base}-hospital-safety-agent`,
      runtime: lambda.Runtime.PYTHON_3_12,
      entry: path.join(__dirname, "../../gateway/tools/hospital_safety_agent"),
      handler: "handler",
      index: "safety_agent_lambda.py",
      timeout: cdk.Duration.minutes(5),
      environment: {
        STACK_NAME: config.stack_name_base,
      },
      logGroup: new logs.LogGroup(this, "SafetyAgentLambdaLogGroup", {
        logGroupName: `/aws/lambda/${config.stack_name_base}-hospital-safety-agent`,
        retention: logs.RetentionDays.ONE_WEEK,
        removalPolicy: cdk.RemovalPolicy.DESTROY,
      }),
    })

    // Grant Lambda permissions to read SSM parameters and secrets
    safetyAgentLambda.addToRolePolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: ["ssm:GetParameter", "ssm:GetParameters"],
        resources: [
          `arn:aws:ssm:${this.region}:${this.account}:parameter/${config.stack_name_base}/*`,
        ],
      })
    )

    safetyAgentLambda.addToRolePolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: ["secretsmanager:GetSecretValue"],
        resources: [
          `arn:aws:secretsmanager:${this.region}:${this.account}:secret:/${config.stack_name_base}/*`,
        ],
      })
    )

    // Grant Gateway permission to invoke the Lambda
    const gatewayRole = iam.Role.fromRoleArn(
      this,
      "ImportedGatewayRole",
      gateway.roleArn!
    )
    safetyAgentLambda.grantInvoke(gatewayRole)

    // Load tool specification
    const toolSpecPath = path.join(
      __dirname,
      "../../gateway/tools/hospital_safety_agent/tool_spec.json"
    )
    const safetyToolSpec = JSON.parse(require("fs").readFileSync(toolSpecPath, "utf8"))

    // Create Gateway Target with Lambda wrapper
    const safetyAgentTarget = new bedrockagentcore.CfnGatewayTarget(
      this,
      "SafetyAgentMcpTarget",
      {
        gatewayIdentifier: gateway.attrGatewayIdentifier,
        name: "hospital-safety-agent-mcp",
        description: "Hospital Safety Agent exposed as MCP tool via Lambda wrapper",
        targetConfiguration: {
          mcp: {
            lambda: {
              lambdaArn: safetyAgentLambda.functionArn,
              toolSchema: {
                inlinePayload: safetyToolSpec,
              },
            },
          },
        },
        credentialProviderConfigurations: [
          {
            credentialProviderType: "GATEWAY_IAM_ROLE",
          },
        ],
      }
    )

    // Ensure proper creation order
    safetyAgentTarget.addDependency(gateway)
    safetyAgentTarget.node.addDependency(this.agentRuntime)
    safetyAgentTarget.node.addDependency(safetyAgentLambda)

    // Outputs
    new cdk.CfnOutput(this, "SafetyAgentLambdaArn", {
      value: safetyAgentLambda.functionArn,
      description: "ARN of the Hospital Safety Agent Lambda wrapper",
    })

    new cdk.CfnOutput(this, "SafetyAgentTargetId", {
      value: safetyAgentTarget.ref,
      description: "Hospital Safety Agent MCP Target ID",
    })
  }

  private createHealthLakeMcpServer(
    gateway: bedrockagentcore.CfnGateway,
    config: AppConfig
  ): void {
    const readOnlyMode = config.backend?.healthlake?.read_only_mode ?? true

    // Create Lambda for HealthLake tools
    const healthLakeLambda = new PythonFunction(this, "HealthLakeToolsLambda", {
      functionName: `${config.stack_name_base}-healthlake-tools`,
      runtime: lambda.Runtime.PYTHON_3_12,
      entry: path.join(__dirname, "../../gateway/tools/healthlake_tools"),
      handler: "handler",
      index: "healthlake_lambda.py",
      timeout: cdk.Duration.minutes(5),
      environment: {
        HEALTHLAKE_READONLY: readOnlyMode.toString(),
        HEALTHLAKE_REGION: config.backend?.healthlake?.region || 'us-east-1',
        HEALTHLAKE_DATASTORE_ID: config.backend?.healthlake?.datastore_id || '',
      },
      logGroup: new logs.LogGroup(this, "HealthLakeToolsLambdaLogGroup", {
        logGroupName: `/aws/lambda/${config.stack_name_base}-healthlake-tools`,
        retention: logs.RetentionDays.ONE_WEEK,
        removalPolicy: cdk.RemovalPolicy.DESTROY,
      }),
    })

    // Grant HealthLake read permissions
    healthLakeLambda.addToRolePolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: [
          'healthlake:ListFHIRDatastores',
          'healthlake:DescribeFHIRDatastore',
          'healthlake:ReadResource',
          'healthlake:SearchWithGet',
          'healthlake:SearchWithPost',
        ],
        resources: ['*'],
      })
    )

    // Add write permissions if not in read-only mode
    if (!readOnlyMode) {
      healthLakeLambda.addToRolePolicy(
        new iam.PolicyStatement({
          effect: iam.Effect.ALLOW,
          actions: [
            'healthlake:CreateResource',
            'healthlake:UpdateResource',
            'healthlake:DeleteResource',
          ],
          resources: ['*'],
        })
      )
    }

    // Grant Gateway permission to invoke the Lambda
    const gatewayRole = iam.Role.fromRoleArn(
      this,
      "ImportedGatewayRoleForHealthLake",
      gateway.roleArn!
    )
    healthLakeLambda.grantInvoke(gatewayRole)

    // Load tool specification
    const toolSpecPath = path.join(__dirname, "../../gateway/tools/healthlake_tools/tool_spec.json")
    const healthLakeToolSpec = JSON.parse(require("fs").readFileSync(toolSpecPath, "utf8"))

    // Create Gateway Target with Lambda
    const healthLakeTarget = new bedrockagentcore.CfnGatewayTarget(
      this,
      "HealthLakeToolsTarget",
      {
        gatewayIdentifier: gateway.attrGatewayIdentifier,
        name: "healthlake-tools",
        description: `AWS HealthLake FHIR tools (${readOnlyMode ? 'read-only' : 'read-write'} mode)`,
        targetConfiguration: {
          mcp: {
            lambda: {
              lambdaArn: healthLakeLambda.functionArn,
              toolSchema: {
                inlinePayload: healthLakeToolSpec,
              },
            },
          },
        },
        credentialProviderConfigurations: [
          {
            credentialProviderType: "GATEWAY_IAM_ROLE",
          },
        ],
      }
    )

    // Ensure proper creation order
    healthLakeTarget.addDependency(gateway)
    healthLakeTarget.node.addDependency(healthLakeLambda)

    // Outputs
    new cdk.CfnOutput(this, "HealthLakeToolsLambdaArn", {
      value: healthLakeLambda.functionArn,
      description: "ARN of the HealthLake Tools Lambda",
    })

    new cdk.CfnOutput(this, "HealthLakeTargetId", {
      value: healthLakeTarget.ref,
      description: "HealthLake Tools Gateway Target ID",
    })

    new cdk.CfnOutput(this, "HealthLakeReadOnlyMode", {
      value: readOnlyMode.toString(),
      description: "Whether HealthLake tools are in read-only mode",
    })
  }


  /**
   * Recursively read directory contents and encode as base64.
   *
   * @param dirPath - Directory to read.
   * @param prefix - Prefix for file paths in output.
   * @param output - Output object to populate.
   */
  private readDirRecursive(dirPath: string, prefix: string, output: Record<string, string>): void {
    for (const entry of fs.readdirSync(dirPath, { withFileTypes: true })) {
      const fullPath = path.join(dirPath, entry.name)
      const relativePath = path.join(prefix, entry.name)

      if (entry.isDirectory()) {
        // Skip __pycache__ directories
        if (entry.name !== "__pycache__") {
          this.readDirRecursive(fullPath, relativePath, output)
        }
      } else if (entry.isFile()) {
        const content = fs.readFileSync(fullPath)
        output[relativePath] = content.toString("base64")
      }
    }
  }

  /**
   * Create a hash of content for change detection.
   *
   * @param content - Content to hash.
   * @returns Hash string.
   */
  private hashContent(content: string): string {
    const crypto = require("crypto")
    return crypto.createHash("sha256").update(content).digest("hex").slice(0, 16)
  }

  /**
   * Creates Bedrock Prompt Management prompts for each agent pattern and stores
   * the versioned ARNs in SSM so agents can fetch them at runtime.
   *
   * @param config - Application configuration
   * @param agentRole - The IAM role used by the AgentCore runtime (granted GetPrompt)
   * @param pattern - The current agent pattern being deployed
   */
  private createManagedPrompts(config: AppConfig, agentRole: iam.Role, pattern: string): void {
    const medicalCodingPromptText = `You are a medical coding assistant specialized in identifying and suggesting appropriate medical codes.

Your capabilities:
1. Extract medical entities from clinical text using Comprehend Medical
2. Search for relevant ICD-10-CM, CPT, and SNOMED CT codes
3. Provide detailed explanations of codes and their appropriate usage

Workflow:
1. When given clinical text, first use extract_medical_entities to identify key medical concepts
2. Then use search_medical_codes to find relevant codes for each identified entity
3. Present codes with clear explanations and usage guidelines
4. Always verify code appropriateness based on clinical context

Important:
- ICD-10-CM codes are for diagnoses and conditions
- CPT codes are for procedures and services
- SNOMED CT codes are for clinical terminology
- Always consider the clinical context when suggesting codes
- Mention if additional documentation is needed for accurate coding`

    const claimsAssemblyPromptText = `You are a Claims Assembly Agent specializing in healthcare claims validation and EDI 837P generation.

Your responsibilities:
1. Validate all required claim data elements
2. Check compliance with HIPAA 5010 standards
3. Verify payer-specific requirements
4. Assemble complete EDI 837P claim structure
5. Flag any missing or invalid data

Available tools:
- query_validation_rules: Search validation rules and payer requirements
- Memory: Access conversation history and previous validations

When assembling claims:
- Validate ALL required fields before assembly
- Check for common errors (invalid NPIs, missing modifiers, etc.)
- Provide clear error messages for any issues
- Generate complete EDI 837P JSON structure
- Confirm readiness for submission

Validation workflow:
1. Check patient demographics (name, DOB, gender, address, MRN)
2. Verify provider credentials (NPI, taxonomy codes, license)
3. Confirm facility information (NPI, address, tax ID)
4. Validate insurance information (policy number, group, eligibility)
5. Check procedure codes (CPT, modifiers, units)
6. Verify diagnosis codes (ICD-10-CM)
7. Perform format and compliance checks
8. Generate EDI 837P JSON structure

Always prioritize accuracy and compliance over speed.`

    const claimsSubmissionPromptText = `You are a Claims Submission Agent specializing in EDI 837P claim submission via AWS B2B Data Interchange.

Your responsibilities:
1. Perform pre-submission readiness checks
2. Submit claims to appropriate payers
3. Monitor submission status
4. Process acknowledgments (997/999)
5. Handle rejections and resubmissions

Available tools:
- check_submission_status: Query B2B Data Interchange for claim status
- retrieve_acknowledgments: Get 997/999 acknowledgments from payers
- submit_claim: Trigger claim submission via B2B Data Interchange
- list_submissions: View recent submission history
- Memory: Access conversation history and submission tracking

When submitting claims:
- Verify claim is ready for submission (all required fields validated)
- Check for duplicate submissions using list_submissions
- Route to correct payer/clearinghouse
- Monitor for acknowledgments after submission
- Handle rejections appropriately with clear explanations
- Provide clear status updates throughout the process

Submission workflow:
1. Verify claim data completeness and validity
2. Check for existing submissions of the same claim (duplicate detection)
3. Submit claim using submit_claim tool
4. Confirm submission with claim ID and timestamp
5. Monitor status using check_submission_status
6. Retrieve and process acknowledgments when available
7. Report any errors or rejections with actionable guidance

Error handling:
- If submission fails, provide specific error details
- If acknowledgment shows rejection, explain rejection reasons
- Suggest corrective actions for common issues
- Track resubmission attempts in memory

Always ensure claims are submitted correctly and track all submissions for audit purposes.`

    const promptConfigs: { id: string; name: string; text: string }[] = [
      { id: "MedicalCoding", name: "medical-coding-agent", text: medicalCodingPromptText },
      { id: "ClaimsAssembly", name: "claims-assembly-agent", text: claimsAssemblyPromptText },
      { id: "ClaimsSubmission", name: "claims-submission-agent", text: claimsSubmissionPromptText },
    ]

    for (const pc of promptConfigs) {
      // Only create prompt resources for the current pattern to avoid cross-stack SSM conflicts
      if (pc.name !== pattern) continue

      const prompt = new bedrock.CfnPrompt(this, `${pc.id}Prompt`, {
        name: `${config.stack_name_base}-${pc.name}-system-prompt`,
        description: `System prompt for the ${pc.name}`,
        variants: [
          {
            name: "default",
            templateType: "TEXT",
            templateConfiguration: {
              text: { text: pc.text },
            },
          },
        ],
      })

      const promptVersion = new bedrock.CfnPromptVersion(this, `${pc.id}PromptVersion`, {
        promptArn: prompt.attrArn,
        description: "Initial version",
      })

      new ssm.StringParameter(this, `${pc.id}PromptArnParam`, {
        parameterName: `/${config.stack_name_base}/prompts/${pc.name}`,
        stringValue: promptVersion.attrArn,
        description: `Versioned ARN for the ${pc.name} system prompt`,
      })
    }

    // Grant the runtime role permission to fetch any prompt in this account
    agentRole.addToPolicy(
      new iam.PolicyStatement({
        sid: "BedrockPromptManagementAccess",
        effect: iam.Effect.ALLOW,
        actions: ["bedrock:GetPrompt"],
        resources: [`arn:aws:bedrock:${this.region}:${this.account}:prompt/*`],
      })
    )
  }

  /**
   * Creates S3 buckets for B2B Data Interchange EDI file exchange.
   * 
   * @param config - Application configuration
   * @returns Object containing input, output, and acknowledgment buckets
   */
  private createB2BIBuckets(config: AppConfig): {
    inputBucket: s3.Bucket
    outputBucket: s3.Bucket
    acknowledgmentBucket: s3.Bucket
  } {
    const inputBucket = new s3.Bucket(this, "B2BIInputBucket", {
      bucketName: `${config.stack_name_base}-b2bi-input-${cdk.Aws.ACCOUNT_ID}`,
      encryption: s3.BucketEncryption.KMS,
      encryptionKey: this.dataEncryptionKey,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      removalPolicy: cdk.RemovalPolicy.RETAIN,
      versioned: true,
      lifecycleRules: [
        {
          id: "DeleteOldClaims",
          enabled: true,
          expiration: cdk.Duration.days(90),
        },
      ],
    })

    const outputBucket = new s3.Bucket(this, "B2BIOutputBucket", {
      bucketName: `${config.stack_name_base}-b2bi-output-${cdk.Aws.ACCOUNT_ID}`,
      encryption: s3.BucketEncryption.KMS,
      encryptionKey: this.dataEncryptionKey,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      removalPolicy: cdk.RemovalPolicy.RETAIN,
      versioned: true,
      lifecycleRules: [
        {
          id: "DeleteOldEDI",
          enabled: true,
          expiration: cdk.Duration.days(90),
        },
      ],
    })

    const acknowledgmentBucket = new s3.Bucket(this, "B2BIAcknowledgmentBucket", {
      bucketName: `${config.stack_name_base}-b2bi-ack-${cdk.Aws.ACCOUNT_ID}`,
      encryption: s3.BucketEncryption.KMS,
      encryptionKey: this.dataEncryptionKey,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      removalPolicy: cdk.RemovalPolicy.RETAIN,
      versioned: true,
      lifecycleRules: [
        {
          id: "DeleteOldAcknowledgments",
          enabled: true,
          expiration: cdk.Duration.days(90),
        },
      ],
    })

    // Store bucket names in SSM
    new ssm.StringParameter(this, "B2BIInputBucketParam", {
      parameterName: `/${config.stack_name_base}/b2bi/input-bucket`,
      stringValue: inputBucket.bucketName,
      description: "B2B Data Interchange input bucket for JSON claims",
    })

    new ssm.StringParameter(this, "B2BIOutputBucketParam", {
      parameterName: `/${config.stack_name_base}/b2bi/output-bucket`,
      stringValue: outputBucket.bucketName,
      description: "B2B Data Interchange output bucket for X12 EDI files",
    })

    new ssm.StringParameter(this, "B2BIAcknowledgmentBucketParam", {
      parameterName: `/${config.stack_name_base}/b2bi/acknowledgment-bucket`,
      stringValue: acknowledgmentBucket.bucketName,
      description: "B2B Data Interchange acknowledgment bucket for 997/999 responses",
    })

    return { inputBucket, outputBucket, acknowledgmentBucket }
  }

  /**
   * Creates B2B Data Interchange profile with organization details.
   * 
   * @param config - Application configuration
   * @returns B2B profile resource
   */
  private createB2BIProfile(config: AppConfig): b2bi.CfnProfile {
    const profile = new b2bi.CfnProfile(this, "B2BIProfile", {
      name: `${config.stack_name_base}-profile`,
      businessName: config.stack_name_base,
      phone: "000-000-0000", // Placeholder - update in config
      email: config.admin_user_email || "admin@example.com",
      logging: "ENABLED",
    })

    // Store profile ID in SSM
    new ssm.StringParameter(this, "B2BIProfileIdParam", {
      parameterName: `/${config.stack_name_base}/b2bi/profile-id`,
      stringValue: profile.attrProfileId,
      description: "B2B Data Interchange profile ID",
    })

    return profile
  }

  /**
   * Creates B2B Data Interchange transformer for JSON to X12 837P conversion.
   * 
   * @param config - Application configuration
   * @returns B2B transformer resource
   */
  private createB2BITransformer(config: AppConfig): b2bi.CfnTransformer {
    // Basic mapping template - to be customized based on requirements
    const mappingTemplate = JSON.stringify({
      // Placeholder mapping - will need to be customized
      note: "This is a placeholder mapping template. Customize based on your EDI 837P requirements.",
    })

    const transformer = new b2bi.CfnTransformer(this, "B2BITransformer", {
      name: `${config.stack_name_base}-837p-transformer`,
      fileFormat: "JSON",
      mappingTemplate: mappingTemplate,
      ediType: {
        x12Details: {
          transactionSet: "X12_837",
          version: "VERSION_5010",
        },
      },
      status: "active",
    })

    // Store transformer ID in SSM
    new ssm.StringParameter(this, "B2BITransformerIdParam", {
      parameterName: `/${config.stack_name_base}/b2bi/transformer-id`,
      stringValue: transformer.attrTransformerId,
      description: "B2B Data Interchange transformer ID for 837P",
    })

    return transformer
  }

  /**
   * Creates B2B Data Interchange capability for automated claim processing.
   * 
   * @param config - Application configuration
   * @param buckets - S3 buckets for B2B Data Interchange
   * @param transformer - B2B transformer resource
   * @returns B2B capability resource
   */
  private createB2BICapability(
    config: AppConfig,
    buckets: { inputBucket: s3.Bucket; outputBucket: s3.Bucket },
    transformer: b2bi.CfnTransformer
  ): b2bi.CfnCapability {
    const capability = new b2bi.CfnCapability(this, "B2BICapability", {
      name: `${config.stack_name_base}-claims-submission`,
      type: "edi",
      configuration: {
        edi: {
          type: {
            x12Details: {
              transactionSet: "X12_837",
              version: "VERSION_5010",
            },
          },
          inputLocation: {
            bucketName: buckets.inputBucket.bucketName,
            key: "claims-to-submit/",
          },
          outputLocation: {
            bucketName: buckets.outputBucket.bucketName,
            key: "submitted-claims/",
          },
          transformerId: transformer.attrTransformerId,
        },
      },
    })

    // Ensure capability is created after transformer
    capability.node.addDependency(transformer)

    // Store capability ID in SSM
    new ssm.StringParameter(this, "B2BICapabilityIdParam", {
      parameterName: `/${config.stack_name_base}/b2bi/capability-id`,
      stringValue: capability.attrCapabilityId,
      description: "B2B Data Interchange capability ID for claims submission",
    })

    return capability
  }

  /**
   * Creates S3 bucket for validation rules Knowledge Base.
   * 
   * @param config - Application configuration
   * @returns S3 bucket for validation rules
   */
  private createValidationKnowledgeBaseBucket(config: AppConfig): s3.Bucket {
    const bucket = new s3.Bucket(this, "ValidationRulesKBBucket", {
      bucketName: `${config.stack_name_base}-validation-kb-${cdk.Aws.ACCOUNT_ID}`,
      encryption: s3.BucketEncryption.S3_MANAGED,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      removalPolicy: cdk.RemovalPolicy.RETAIN,
      versioned: true,
    })

    new cdk.CfnOutput(this, "ValidationKBBucket", {
      value: bucket.bucketName,
      description: "S3 bucket for validation rules knowledge base",
    })

    // Store bucket name in SSM
    new ssm.StringParameter(this, "ValidationKBBucketParam", {
      parameterName: `/${config.stack_name_base}/validation-kb-bucket`,
      stringValue: bucket.bucketName,
      description: "S3 bucket for validation rules knowledge base",
    })

    return bucket
  }

  /**
   * Creates B2B Data Interchange integration Lambda and Gateway target.
   * 
   * @param config - Application configuration
   * @param gateway - AgentCore Gateway instance
   * @param gatewayRole - Gateway IAM role
   * @param buckets - B2B S3 buckets
   */
  private createB2BIIntegrationTarget(
    config: AppConfig,
    gateway: bedrockagentcore.CfnGateway,
    gatewayRole: iam.Role,
    buckets: { inputBucket: s3.Bucket; outputBucket: s3.Bucket; acknowledgmentBucket: s3.Bucket }
  ): void {
    // Create Lambda function
    const b2biLambda = new lambda.Function(this, "B2BIIntegrationLambda", {
      functionName: `${config.stack_name_base}-b2bi-integration`,
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: "lambda_handler.lambda_handler",
      code: lambda.Code.fromAsset(
        path.join(__dirname, "../../gateway/tools/b2bi_integration"),
      ),
      timeout: cdk.Duration.seconds(30),
      memorySize: 512,
      environment: {
        LOG_LEVEL: "INFO",
        B2BI_TRANSFORMER_ID: this.b2biTransformerId || "",
        B2BI_INPUT_BUCKET: buckets.inputBucket.bucketName,
        B2BI_OUTPUT_BUCKET: buckets.outputBucket.bucketName,
        B2BI_ACKNOWLEDGMENT_BUCKET: buckets.acknowledgmentBucket.bucketName,
      },
    })

    // Grant B2B Data Interchange permissions
    b2biLambda.addToRolePolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: [
          "b2bi:GetTransformer",
          "b2bi:StartTransformerJob",
          "b2bi:ListTransformerJobs",
        ],
        resources: ["*"],
      }),
    )

    // Grant S3 permissions
    buckets.inputBucket.grantPut(b2biLambda)
    buckets.outputBucket.grantRead(b2biLambda)
    buckets.acknowledgmentBucket.grantRead(b2biLambda)
    buckets.inputBucket.grantRead(b2biLambda) // For listing
    buckets.outputBucket.grantRead(b2biLambda) // For listing
    buckets.acknowledgmentBucket.grantRead(b2biLambda) // For listing

    // Define tool schemas
    const toolSchemas = [
      {
        name: "check_submission_status",
        description: "Check status of claim submission in B2B Data Interchange",
        inputSchema: {
          type: "object",
          properties: {
            claim_id: {
              type: "string",
              description: "Unique claim identifier",
            },
          },
          required: ["claim_id"],
        },
      },
      {
        name: "retrieve_acknowledgments",
        description: "Retrieve 997/999 acknowledgments from payers for a claim",
        inputSchema: {
          type: "object",
          properties: {
            claim_id: {
              type: "string",
              description: "Unique claim identifier",
            },
          },
          required: ["claim_id"],
        },
      },
      {
        name: "submit_claim",
        description: "Submit claim to B2B Data Interchange for EDI transformation",
        inputSchema: {
          type: "object",
          properties: {
            claim_data: {
              type: "object",
              description: "Claim data in JSON format (EDI 837P structure)",
            },
            claim_id: {
              type: "string",
              description: "Unique claim identifier",
            },
          },
          required: ["claim_data", "claim_id"],
        },
      },
      {
        name: "list_submissions",
        description: "List recent claim submissions and their status",
        inputSchema: {
          type: "object",
          properties: {
            limit: {
              type: "integer",
              description: "Maximum number of submissions to return (default: 10)",
            },
          },
        },
      },
    ]

    // Create Gateway target
    new bedrockagentcore.CfnGatewayTarget(this, "B2BIIntegrationTarget", {
      gatewayIdentifier: gateway.attrGatewayIdentifier,
      name: "b2bi-integration-target",
      description: "B2B Data Interchange tools for claim submission and tracking",
      targetConfiguration: {
        mcp: {
          lambda: {
            lambdaArn: b2biLambda.functionArn,
            toolSchema: {
              inlinePayload: toolSchemas as any,
            },
          },
        },
      },
      credentialProviderConfigurations: [
        {
          credentialProviderType: "GATEWAY_IAM_ROLE",
        },
      ],
    })

    // Grant Gateway role permission to invoke Lambda
    b2biLambda.grantInvoke(gatewayRole)
  }
}
