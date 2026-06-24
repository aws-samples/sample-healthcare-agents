import * as cdk from "aws-cdk-lib"
import * as iam from "aws-cdk-lib/aws-iam"
import * as lambda from "aws-cdk-lib/aws-lambda"
import * as logs from "aws-cdk-lib/aws-logs"
import * as bedrockagentcore from "aws-cdk-lib/aws-bedrockagentcore"
import * as dynamodb from "aws-cdk-lib/aws-dynamodb"
import * as apigateway from "aws-cdk-lib/aws-apigateway"
import * as cognito from "aws-cdk-lib/aws-cognito"
import * as ssm from "aws-cdk-lib/aws-ssm"
import * as kms from "aws-cdk-lib/aws-kms"
import * as secretsmanager from "aws-cdk-lib/aws-secretsmanager"
import { Construct } from "constructs"
import { AppConfig } from "./utils/config-manager"
import * as path from "path"
import { PythonFunction } from "@aws-cdk/aws-lambda-python-alpha"

// Import nested stacks
import { AmplifyHostingStack } from "./amplify-hosting-stack"
import { CognitoStack } from "./cognito-stack"

export interface HealthcareAgentsMainStackProps extends cdk.StackProps {
  config: AppConfig
}

/**
 * Main Stack - Shared Infrastructure
 *
 * This stack creates the shared infrastructure that all agent patterns use:
 * - Amplify Hosting for the frontend
 * - Cognito for authentication
 * - Shared AgentCore Gateway (all agents access the same tools)
 *
 * Backend stacks for each agent pattern are created separately in bin/fast-cdk.ts
 */
export class HealthcareAgentsMainStack extends cdk.Stack {
  public readonly amplifyHostingStack: AmplifyHostingStack
  public readonly cognitoStack: CognitoStack
  public readonly sharedGateway: bedrockagentcore.CfnGateway
  public readonly sharedGatewayRole: iam.Role
  public readonly machineClient: cdk.aws_cognito.UserPoolClient
  // Payor-policy tool Lambda — the canonical prior-auth requirement rule source,
  // invoked by both the Prior Auth Agent (via Gateway) and CDS Hooks order-select.
  private payorPolicyLambda!: PythonFunction

  constructor(scope: Construct, id: string, props: HealthcareAgentsMainStackProps) {
    const description = "Healthcare Agents on AgentCore - Shared Infrastructure (v0.3.0) (uksb-v6dos0t5g8)"
    super(scope, id, { ...props, description })

    // Create the Amplify stack to get the predictable domain
    this.amplifyHostingStack = new AmplifyHostingStack(this, `${id}-amplify`, {
      config: props.config,
    })

    // Create Cognito for authentication
    this.cognitoStack = new CognitoStack(this, `${id}-cognito`, {
      config: props.config,
      callbackUrls: ["http://localhost:3000", this.amplifyHostingStack.amplifyUrl],
    })

    // Create machine-to-machine client for Gateway authentication
    this.machineClient = this.createMachineClient(props.config)

    // Create shared AgentCore Gateway (used by all agent patterns)
    const gatewayResources = this.createSharedGateway(props.config)
    this.sharedGateway = gatewayResources.gateway
    this.sharedGatewayRole = gatewayResources.gatewayRole

    // Create shared Gateway Targets (tools) that all patterns can use
    this.createHealthLakeTools(props.config, this.sharedGateway, this.sharedGatewayRole)
    this.createComprehendMedicalTools(props.config, this.sharedGateway, this.sharedGatewayRole)
    this.createPayorPolicyTools(props.config, this.sharedGateway, this.sharedGatewayRole)
    this.createEpicFHIRTools(props.config, this.sharedGateway, this.sharedGatewayRole)
    this.createAppealsKBTools(props.config, this.sharedGateway, this.sharedGatewayRole)

    // Create shared platform-level feedback infrastructure (one table + API for all patterns)
    const userPool = cognito.UserPool.fromUserPoolId(
      this,
      "ImportedUserPoolForFeedback",
      this.cognitoStack.userPoolId
    )
    this.createPlatformFeedback(props.config, this.amplifyHostingStack.amplifyUrl, userPool)

    // Create public CDS Hooks REST endpoint for EHR / CDS Hooks Sandbox integration
    this.createCdsHooksApi(props.config, this.amplifyHostingStack.amplifyUrl)

    // Create shared Langfuse observability secret (used by all agent patterns)
    this.createLangfuseSecret(props.config)

    // Create shared Cognito SSM parameters (used by all agent patterns)
    this.createCognitoSSMParameters(props.config)

    // Create Bedrock Guardrail for PHI masking in traces
    this.createPhiGuardrail(props.config)

    // Note: Backend stacks for each agent pattern are created separately in bin/fast-cdk.ts
    // Note: SafetyAnalysisStack is deployed independently (see bin/fast-cdk.ts)
    // It looks up DynamoDB tables via SSM parameters and can be deployed separately

    // Outputs - Shared Infrastructure
    new cdk.CfnOutput(this, "AmplifyAppId", {
      value: this.amplifyHostingStack.amplifyApp.appId,
      description: "Amplify App ID - use this for manual deployment",
      exportName: `${props.config.stack_name_base}-AmplifyAppId`,
    })

    new cdk.CfnOutput(this, "AmplifyConsoleUrl", {
      value: `https://console.aws.amazon.com/amplify/apps/${this.amplifyHostingStack.amplifyApp.appId}`,
      description: "Amplify Console URL for monitoring deployments",
    })

    new cdk.CfnOutput(this, "AmplifyUrl", {
      value: this.amplifyHostingStack.amplifyUrl,
      description: "Amplify Frontend URL (available after deployment)",
      exportName: `${props.config.stack_name_base}-AmplifyUrl`,
    })

    new cdk.CfnOutput(this, "StagingBucketName", {
      value: this.amplifyHostingStack.stagingBucket.bucketName,
      description: "S3 bucket for Amplify deployment staging",
      exportName: `${props.config.stack_name_base}-StagingBucket`,
    })

    new cdk.CfnOutput(this, "CognitoUserPoolId", {
      value: this.cognitoStack.userPoolId,
      description: "Cognito User Pool ID",
      exportName: `${props.config.stack_name_base}-CognitoUserPoolId`,
    })

    new cdk.CfnOutput(this, "CognitoClientId", {
      value: this.cognitoStack.userPoolClientId,
      description: "Cognito User Pool Client ID",
      exportName: `${props.config.stack_name_base}-CognitoClientId`,
    })

    new cdk.CfnOutput(this, "CognitoDomain", {
      value: `${this.cognitoStack.userPoolDomain.domainName}.auth.${cdk.Aws.REGION}.amazoncognito.com`,
      description: "Cognito Domain for OAuth",
      exportName: `${props.config.stack_name_base}-CognitoDomain`,
    })

    new cdk.CfnOutput(this, "SharedGatewayId", {
      value: this.sharedGateway.attrGatewayIdentifier,
      description: "Shared Gateway ID (used by all agent patterns)",
      exportName: `${props.config.stack_name_base}-SharedGatewayId`,
    })

    new cdk.CfnOutput(this, "SharedGatewayUrl", {
      value: this.sharedGateway.attrGatewayUrl,
      description: "Shared Gateway URL",
      exportName: `${props.config.stack_name_base}-SharedGatewayUrl`,
    })

    new cdk.CfnOutput(this, "MachineClientId", {
      value: this.machineClient.userPoolClientId,
      description: "Shared Machine Client ID for M2M authentication (used by all patterns)",
      exportName: `${props.config.stack_name_base}-MachineClientId`,
    })
  }

  /**
   * Create machine-to-machine Cognito client for Gateway authentication
   */
  private createMachineClient(config: AppConfig): cdk.aws_cognito.UserPoolClient {
    const userPool = cdk.aws_cognito.UserPool.fromUserPoolId(
      this,
      "UserPool",
      this.cognitoStack.userPoolId
    )

    // Create resource server for M2M authentication
    const resourceServer = new cdk.aws_cognito.UserPoolResourceServer(this, "ResourceServer", {
      userPool,
      identifier: `${config.stack_name_base}-api`,
      scopes: [
        {
          scopeName: "invoke",
          scopeDescription: "Invoke agent runtime and gateway",
        },
      ],
    })

    const invokeScope = new cdk.aws_cognito.ResourceServerScope({
      scopeName: "invoke",
      scopeDescription: "Invoke agent runtime and gateway",
    })

    // Create machine client with client credentials flow
    const machineClient = new cdk.aws_cognito.UserPoolClient(this, "MachineClient", {
      userPool,
      generateSecret: true,
      authFlows: {
        userPassword: false,
        userSrp: false,
        custom: false,
      },
      oAuth: {
        flows: {
          clientCredentials: true,
        },
        scopes: [cdk.aws_cognito.OAuthScope.resourceServer(resourceServer, invokeScope)],
      },
    })

    // Store machine client credentials in SSM/Secrets Manager (shared by all patterns)
    new ssm.StringParameter(this, "MachineClientIdParam", {
      parameterName: `/${config.stack_name_base}/machine_client_id`,
      stringValue: machineClient.userPoolClientId,
      description: "Shared Machine Client ID for M2M authentication (used by all patterns)",
    })

    new secretsmanager.Secret(this, "MachineClientSecret", {
      secretName: `/${config.stack_name_base}/machine_client_secret`,
      secretStringValue: cdk.SecretValue.unsafePlainText(machineClient.userPoolClientSecret.unsafeUnwrap()),
      description: "Shared Machine Client Secret for M2M authentication (used by all patterns)",
    })

    return machineClient
  }

  /**
   * Create shared AgentCore Gateway with all tools
   * This Gateway is used by ALL agent patterns
   */
  private createSharedGateway(config: AppConfig): {
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

    // Create IAM role for Gateway
    const gatewayRole = new iam.Role(this, "SharedGatewayRole", {
      assumedBy: new iam.ServicePrincipal("bedrock-agentcore.amazonaws.com"),
      description: "Shared Gateway role for all agent patterns",
    })

    // Lambda invoke permissions
    gatewayRole.addToPolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: ["lambda:InvokeFunction"],
        resources: [toolLambda.functionArn, `${toolLambda.functionArn}:*`],
      })
    )

    // SSM permissions for config lookup
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
    const userPool = cdk.aws_cognito.UserPool.fromUserPoolId(
      this,
      "UserPoolForGateway",
      this.cognitoStack.userPoolId
    )
    gatewayRole.addToPolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: ["cognito-idp:DescribeUserPoolClient", "cognito-idp:InitiateAuth"],
        resources: [userPool.userPoolArn],
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

    // Load tool specification
    const toolSpecPath = path.join(__dirname, "../../gateway/tools/sample_tool/tool_spec.json")
    const apiSpec = JSON.parse(require("fs").readFileSync(toolSpecPath, "utf8"))

    // Cognito OAuth2 configuration
    const cognitoIssuer = `https://cognito-idp.${this.region}.amazonaws.com/${this.cognitoStack.userPoolId}`
    const cognitoDiscoveryUrl = `${cognitoIssuer}/.well-known/openid-configuration`

    // Create Gateway (updated with MCP 2025-11-25 support for authorization code grant)
    const gateway = new bedrockagentcore.CfnGateway(this, "SharedAgentCoreGateway", {
      name: `${config.stack_name_base}-shared-gateway`,
      roleArn: gatewayRole.roleArn,
      protocolType: "MCP",
      protocolConfiguration: {
        mcp: {
          supportedVersions: ["2025-03-26"],
        },
      },
      authorizerType: "CUSTOM_JWT",
      authorizerConfiguration: {
        customJwtAuthorizer: {
          allowedClients: [this.machineClient.userPoolClientId],
          discoveryUrl: cognitoDiscoveryUrl,
        },
      },
      description: "Shared Gateway for all agent patterns - Epic FHIR, HealthLake, and other tools",
    })

    // Create Gateway Target for sample tool
    new bedrockagentcore.CfnGatewayTarget(this, "SharedGatewayTarget", {
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

    // Grant Lambda invoke permission to Gateway
    toolLambda.grantInvoke(gatewayRole)

    // Store Gateway URL in SSM for easy lookup
    new cdk.aws_ssm.StringParameter(this, "SharedGatewayUrlParam", {
      parameterName: `/${config.stack_name_base}/shared-gateway-url`,
      stringValue: gateway.attrGatewayUrl,
      description: "Shared Gateway URL for all agent patterns",
    })

    // Store Amplify URL in SSM for OAuth callbacks
    new cdk.aws_ssm.StringParameter(this, "AmplifyUrlParam", {
      parameterName: `/${config.stack_name_base}/amplify-url`,
      stringValue: this.amplifyHostingStack.amplifyUrl,
      description: "Amplify frontend URL for OAuth callbacks",
    })

    return { gateway, gatewayRole }
  }

  /**
   * Create HealthLake Tools Gateway Target (shared across all patterns)
   */
  private createHealthLakeTools(
    config: AppConfig,
    gateway: bedrockagentcore.CfnGateway,
    gatewayRole: iam.Role
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
        HEALTHLAKE_REGION: config.backend?.healthlake?.region || "us-east-1",
        HEALTHLAKE_DATASTORE_ID: config.backend?.healthlake?.datastore_id || "",
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
          "healthlake:ListFHIRDatastores",
          "healthlake:DescribeFHIRDatastore",
          "healthlake:ReadResource",
          "healthlake:SearchWithGet",
          "healthlake:SearchWithPost",
          // Required by the get_patient_everything tool ($patient-everything operation)
          "healthlake:SearchEverything",
        ],
        resources: ["*"],
      })
    )

    // Create-only write permission (option 1): lets the create_fhir_resource
    // tool persist decisions (e.g. a ClaimResponse) to HealthLake. Update and
    // Delete are intentionally NOT granted, regardless of read_only_mode.
    healthLakeLambda.addToRolePolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: ["healthlake:CreateResource"],
        resources: ["*"],
      })
    )

    // Add write permissions if not in read-only mode
    if (!readOnlyMode) {
      healthLakeLambda.addToRolePolicy(
        new iam.PolicyStatement({
          effect: iam.Effect.ALLOW,
          actions: [
            "healthlake:CreateResource",
            "healthlake:UpdateResource",
            "healthlake:DeleteResource",
          ],
          resources: ["*"],
        })
      )
    }

    // Grant Gateway permission to invoke the Lambda
    healthLakeLambda.grantInvoke(gatewayRole)

    // Load tool specification
    const toolSpecPath = path.join(
      __dirname,
      "../../gateway/tools/healthlake_tools/tool_spec.json"
    )
    const healthLakeToolSpec = JSON.parse(
      require("fs").readFileSync(toolSpecPath, "utf8")
    )

    // Create Gateway Target with Lambda
    const healthLakeTarget = new bedrockagentcore.CfnGatewayTarget(
      this,
      "HealthLakeToolsTarget",
      {
        gatewayIdentifier: gateway.attrGatewayIdentifier,
        name: "healthlake-tools",
        description: `AWS HealthLake FHIR tools (${readOnlyMode ? "read-only" : "read-write"} mode)`,
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

    new cdk.CfnOutput(this, "HealthLakeToolsTargetId", {
      value: healthLakeTarget.ref,
      description: "HealthLake Tools MCP Target ID",
    })
  }

  /**
   * Create Comprehend Medical Tools Gateway Target (used by medical-coding-agent)
   */
  private createComprehendMedicalTools(
    config: AppConfig,
    gateway: bedrockagentcore.CfnGateway,
    gatewayRole: iam.Role
  ): void {
    // Create Lambda function
    const comprehendLambda = new lambda.Function(this, "ComprehendMedicalLambda", {
      functionName: `${config.stack_name_base}-comprehend-medical`,
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: "lambda_handler.lambda_handler",
      code: lambda.Code.fromAsset(
        path.join(__dirname, "../../gateway/tools/comprehend_medical")
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
      })
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

    // Grant Gateway role permission to invoke Lambda BEFORE creating target
    comprehendLambda.grantInvoke(gatewayRole)

    // Create Gateway target
    const comprehendTarget = new bedrockagentcore.CfnGatewayTarget(this, "ComprehendMedicalTarget", {
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

    // Ensure proper creation order
    comprehendTarget.node.addDependency(comprehendLambda)
  }

  private createAppealsKBTools(
    config: AppConfig,
    gateway: bedrockagentcore.CfnGateway,
    gatewayRole: iam.Role
  ): void {
    const appealsLambda = new lambda.Function(this, "AppealsKBLambda", {
      functionName: `${config.stack_name_base}-appeals-kb-tools`,
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: "appeals_kb_lambda.handler",
      code: lambda.Code.fromAsset(path.join(__dirname, "../../gateway/tools/appeals_kb")),
      timeout: cdk.Duration.seconds(30),
      environment: {
        STACK_NAME: config.stack_name_base,
      },
    })

    // Grant bedrock:Retrieve on the appeals KB
    appealsLambda.addToRolePolicy(new iam.PolicyStatement({
      actions: ["bedrock:Retrieve"],
      resources: [`arn:aws:bedrock:${this.region}:${this.account}:knowledge-base/*`],
    }))

    // Grant SSM read so Lambda can look up the KB ID at runtime
    appealsLambda.addToRolePolicy(new iam.PolicyStatement({
      actions: ["ssm:GetParameter"],
      resources: [`arn:aws:ssm:${this.region}:${this.account}:parameter/${config.stack_name_base}/appeals-kb-id`],
    }))

    const toolSpec = JSON.parse(
      require("fs").readFileSync(
        path.join(__dirname, "../../gateway/tools/appeals_kb/tool_spec.json"), "utf8"
      )
    )

    appealsLambda.grantInvoke(gatewayRole)

    const appealsTarget = new bedrockagentcore.CfnGatewayTarget(this, "AppealsKBTarget", {
      gatewayIdentifier: gateway.attrGatewayIdentifier,
      name: "appeals-kb-target",
      description: "Appeals KB tools: denial codes, appeal regulations, clinical guidelines",
      targetConfiguration: {
        mcp: {
          lambda: {
            lambdaArn: appealsLambda.functionArn,
            toolSchema: { inlinePayload: toolSpec.tools as any },
          },
        },
      },
      credentialProviderConfigurations: [{ credentialProviderType: "GATEWAY_IAM_ROLE" }],
    })
    appealsTarget.node.addDependency(appealsLambda)
  }

  /**
   * Create Payor Policy Tools Gateway Target (used by prior-authorization-agent).
   *
   * Exposes lookup_prior_auth_requirements, search_payor_policies,
   * list_policy_documents, upload_policy_document over the Gateway so the
   * Prior Auth Agent can ground its Step-2 prior-auth requirement check.
   * Without a configured Bedrock Knowledge Base, lookup_prior_auth_requirements
   * still returns results from its built-in CPT reference table.
   */
  private createPayorPolicyTools(
    config: AppConfig,
    gateway: bedrockagentcore.CfnGateway,
    gatewayRole: iam.Role
  ): void {
    const payorPolicyLambda = new PythonFunction(this, "PayorPolicyLambda", {
      functionName: `${config.stack_name_base}-payor-policy`,
      runtime: lambda.Runtime.PYTHON_3_12,
      entry: path.join(__dirname, "../../gateway/tools/payor_policy"),
      handler: "handler",
      index: "payor_policy_lambda.py",
      timeout: cdk.Duration.seconds(30),
      memorySize: 512,
      environment: {
        // POLICY_KB_ID / POLICY_BUCKET / POLICY_DATA_SOURCE_ID are optional.
        // When unset, the KB-backed search degrades gracefully and the
        // requirement lookup uses its built-in CPT table.
        LOG_LEVEL: "INFO",
      },
      logGroup: new logs.LogGroup(this, "PayorPolicyLambdaLogGroup", {
        logGroupName: `/aws/lambda/${config.stack_name_base}-payor-policy`,
        retention: logs.RetentionDays.ONE_WEEK,
        removalPolicy: cdk.RemovalPolicy.DESTROY,
      }),
    })

    // Expose for reuse (CDS Hooks order-select delegates to this rule source)
    this.payorPolicyLambda = payorPolicyLambda

    // Allow Bedrock Knowledge Base retrieval + ingestion when a KB is configured
    // (no-op at runtime until POLICY_KB_ID/POLICY_BUCKET are set), and InvokeModel
    // for the dynamic prior-auth requirement assessment (no hardcoded drug list).
    payorPolicyLambda.addToRolePolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: [
          "bedrock:Retrieve",
          "bedrock:StartIngestionJob",
          "bedrock:InvokeModel",
        ],
        resources: ["*"],
      })
    )

    payorPolicyLambda.grantInvoke(gatewayRole)

    const payorPolicyToolSpec = JSON.parse(
      require("fs").readFileSync(
        path.join(__dirname, "../../gateway/tools/payor_policy/tool_spec.json"),
        "utf8"
      )
    ).tools

    const payorPolicyTarget = new bedrockagentcore.CfnGatewayTarget(this, "PayorPolicyTarget", {
      gatewayIdentifier: gateway.attrGatewayIdentifier,
      name: "payor-policy",
      description: "Payor prior-authorization policy tools (requirement lookup + policy KB search)",
      targetConfiguration: {
        mcp: {
          lambda: {
            lambdaArn: payorPolicyLambda.functionArn,
            toolSchema: {
              inlinePayload: payorPolicyToolSpec as any,
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

    payorPolicyTarget.addDependency(gateway)
    payorPolicyTarget.node.addDependency(payorPolicyLambda)

    new cdk.CfnOutput(this, "PayorPolicyToolsTargetId", {
      value: payorPolicyTarget.ref,
      description: "Payor Policy MCP Target ID",
    })
  }

  /**
   * Create Epic FHIR tools (3LO User Federation with OAuth2)
   * Uses OpenAPI Gateway Target (not Lambda) to support OAuth credential provider
   */
  private createEpicFHIRTools(
    _config: AppConfig,
    gateway: bedrockagentcore.CfnGateway,
    _gatewayRole: iam.Role
  ): void {
    // Epic FHIR OpenAPI specification
    // Following the pattern from LinkedIn OAuth notebook example
    const epicFhirOpenApiSpec = {
      openapi: "3.0.0",
      info: {
        title: "Epic FHIR API (User Federation)",
        version: "R4",
        description: "Epic FHIR R4 API for user-authorized patient data access",
      },
      servers: [
        {
          url: "https://fhir.epic.com/interconnect-fhir-oauth/api/FHIR/R4",
          description: "Epic FHIR production server",
        },
      ],
      paths: {
        "/Patient/{id}": {
          get: {
            operationId: "get_patient_with_user_auth",
            summary: "Get patient demographics",
            description: "Retrieve patient demographics with user authorization (3LO)",
            parameters: [
              {
                name: "id",
                in: "path",
                required: true,
                schema: { type: "string" },
                description: "FHIR Patient resource ID",
              },
            ],
            security: [{ OAuth2: ["user/Patient.read"] }],
            responses: {
              "200": {
                description: "Patient resource",
                content: {
                  "application/json": {
                    schema: { type: "object" },
                  },
                },
              },
            },
          },
        },
        "/MedicationRequest": {
          get: {
            operationId: "get_medications_with_user_auth",
            summary: "Get patient medications",
            description: "Retrieve active medications with user authorization",
            parameters: [
              {
                name: "patient",
                in: "query",
                required: true,
                schema: { type: "string" },
                description: "Patient ID",
              },
              {
                name: "status",
                in: "query",
                schema: { type: "string", default: "active" },
                description: "Medication status filter",
              },
            ],
            security: [{ OAuth2: ["user/MedicationRequest.read"] }],
            responses: {
              "200": {
                description: "Bundle of MedicationRequest resources",
                content: {
                  "application/json": {
                    schema: { type: "object" },
                  },
                },
              },
            },
          },
        },
        "/AllergyIntolerance": {
          get: {
            operationId: "get_allergies_with_user_auth",
            summary: "Get patient allergies",
            description: "Retrieve allergies and intolerances with user authorization",
            parameters: [
              {
                name: "patient",
                in: "query",
                required: true,
                schema: { type: "string" },
                description: "Patient ID",
              },
            ],
            security: [{ OAuth2: ["user/AllergyIntolerance.read"] }],
            responses: {
              "200": {
                description: "Bundle of AllergyIntolerance resources",
                content: {
                  "application/json": {
                    schema: { type: "object" },
                  },
                },
              },
            },
          },
        },
        "/Observation": {
          get: {
            operationId: "get_observations_with_user_auth",
            summary: "Get patient observations",
            description: "Retrieve observations (labs, vitals) with user authorization",
            parameters: [
              {
                name: "patient",
                in: "query",
                required: true,
                schema: { type: "string" },
                description: "Patient ID",
              },
              {
                name: "category",
                in: "query",
                schema: { type: "string", default: "vital-signs" },
                description: "Observation category (vital-signs, laboratory, etc.)",
              },
            ],
            security: [{ OAuth2: ["user/Observation.read"] }],
            responses: {
              "200": {
                description: "Bundle of Observation resources",
                content: {
                  "application/json": {
                    schema: { type: "object" },
                  },
                },
              },
            },
          },
        },
      },
      components: {
        securitySchemes: {
          OAuth2: {
            type: "oauth2",
            flows: {
              authorizationCode: {
                authorizationUrl: "https://fhir.epic.com/interconnect-fhir-oauth/oauth2/authorize",
                tokenUrl: "https://fhir.epic.com/interconnect-fhir-oauth/oauth2/token",
                scopes: {
                  "user/Patient.read": "Read patient demographics",
                  "user/MedicationRequest.read": "Read medication orders",
                  "user/AllergyIntolerance.read": "Read allergies",
                  "user/Observation.read": "Read observations",
                },
              },
            },
          },
        },
      },
    }

    // Get Epic OAuth Provider ARN from environment variable
    // NOTE: The OAuth credential provider must be created first via AWS CLI:
    // aws bedrock-agentcore-control create-oauth2-credential-provider \
    //   --name EpicFHIRProvider \
    //   --credential-provider-vendor CustomOauth2 \
    //   --oauth2-provider-config-input '{
    //     "customOauth2ProviderConfig": {
    //       "oauthDiscovery": {
    //         "discoveryUrl": "https://fhir.epic.com/interconnect-fhir-oauth/api/FHIR/R4/.well-known/openid-configuration"
    //       },
    //       "clientId": "<YOUR_EPIC_CLIENT_ID>",
    //       "clientSecret": "<YOUR_EPIC_CLIENT_SECRET>"
    //     }
    //   }' \
    //   --region us-east-1
    const epicProviderArn = process.env.EPIC_OAUTH_PROVIDER_ARN ||
      `arn:aws:bedrock-agentcore:${cdk.Aws.REGION}:${cdk.Aws.ACCOUNT_ID}:token-vault/default/oauth2credentialprovider/EpicFHIRProvider`

    // Create OpenAPI Gateway Target with OAuth credential provider
    // Following the exact pattern from the Jupyter notebook
    const epicTarget = new bedrockagentcore.CfnGatewayTarget(this, "EpicFHIRTargetV2", {
      gatewayIdentifier: gateway.attrGatewayIdentifier,
      name: "epic-fhir",
      description: "Epic FHIR API with OAuth2 Authorization Code Grant (3LO)",
      targetConfiguration: {
        mcp: {
          openApiSchema: {
            inlinePayload: JSON.stringify(epicFhirOpenApiSpec),
          },
        },
      },
      credentialProviderConfigurations: [
        {
          credentialProviderType: "OAUTH",
          credentialProvider: {
            oauthCredentialProvider: {
              providerArn: epicProviderArn,
              scopes: [
                "user/Patient.read",
                "user/MedicationRequest.read",
                "user/AllergyIntolerance.read",
                "user/Observation.read",
              ],
            },
          },
        },
      ],
    })

    // Output Epic tools information
    new cdk.CfnOutput(this, "EpicFHIRTargetIdV2", {
      value: epicTarget.name!,
      description: "Gateway target ID for Epic FHIR tools (OpenAPI with OAuth)",
    })

    new cdk.CfnOutput(this, "EpicOAuthProviderArn", {
      value: epicProviderArn,
      description: "Epic OAuth2 credential provider ARN",
    })
  }

  /**
   * Create platform-level feedback infrastructure (shared by all agent patterns)
   */
  private createPlatformFeedback(
    config: AppConfig,
    frontendUrl: string,
    userPool: cognito.IUserPool
  ): void {
    // Create KMS key for encryption
    const dataEncryptionKey = new kms.Key(this, "FeedbackDataEncryptionKey", {
      enableKeyRotation: true,
      description: "KMS key for feedback table encryption",
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    })

    // Create feedback DynamoDB table (shared by all patterns)
    const feedbackTable = new dynamodb.Table(this, "PlatformFeedbackTable", {
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
      encryptionKey: dataEncryptionKey,
      stream: dynamodb.StreamViewType.NEW_IMAGE,
    })

    // Add GSI for querying by pattern
    feedbackTable.addGlobalSecondaryIndex({
      indexName: "pattern-timestamp-index",
      partitionKey: {
        name: "pattern",
        type: dynamodb.AttributeType.STRING,
      },
      sortKey: {
        name: "timestamp",
        type: dynamodb.AttributeType.NUMBER,
      },
      projectionType: dynamodb.ProjectionType.ALL,
    })

    // Add GSI for querying by feedbackType
    feedbackTable.addGlobalSecondaryIndex({
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

    // Create feedback Lambda
    const feedbackLambda = new PythonFunction(this, "PlatformFeedbackLambda", {
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
          `arn:aws:lambda:${cdk.Stack.of(this).region}:017000801446:layer:AWSLambdaPowertoolsPythonV3-python313-arm64:18`
        ),
      ],
      logGroup: new logs.LogGroup(this, "PlatformFeedbackLambdaLogGroup", {
        logGroupName: `/aws/lambda/${config.stack_name_base}-feedback`,
        retention: logs.RetentionDays.ONE_WEEK,
        removalPolicy: cdk.RemovalPolicy.DESTROY,
      }),
    })

    // Grant Lambda permissions
    feedbackTable.grantWriteData(feedbackLambda)

    // Create API Gateway
    const api = new apigateway.RestApi(this, "PlatformFeedbackApi", {
      restApiName: `${config.stack_name_base}-feedback-api`,
      description: "Platform-level feedback API for all agent patterns",
      defaultCorsPreflightOptions: {
        allowOrigins: [frontendUrl, "http://localhost:3000"],
        allowMethods: ["GET", "POST", "OPTIONS"],
        allowHeaders: ["Content-Type", "Authorization"],
      },
      deployOptions: {
        stageName: "prod",
        throttlingRateLimit: 100,
        throttlingBurstLimit: 200,
        loggingLevel: apigateway.MethodLoggingLevel.INFO,
        dataTraceEnabled: false,
        metricsEnabled: true,
        accessLogDestination: new apigateway.LogGroupLogDestination(
          new logs.LogGroup(this, "PlatformFeedbackApiAccessLogGroup", {
            logGroupName: `/aws/apigateway/${config.stack_name_base}-feedback-api-access`,
            retention: logs.RetentionDays.ONE_WEEK,
            removalPolicy: cdk.RemovalPolicy.DESTROY,
          })
        ),
        accessLogFormat: apigateway.AccessLogFormat.jsonWithStandardFields(),
        tracingEnabled: true,
      },
    })

    // Add request validator
    const requestValidator = new apigateway.RequestValidator(
      this,
      "PlatformFeedbackApiRequestValidator",
      {
        restApi: api,
        requestValidatorName: `${config.stack_name_base}-feedback-request-validator`,
        validateRequestBody: true,
        validateRequestParameters: true,
      }
    )

    // Create Cognito authorizer
    const authorizer = new apigateway.CognitoUserPoolsAuthorizer(
      this,
      "PlatformFeedbackApiAuthorizer",
      {
        cognitoUserPools: [userPool],
        identitySource: "method.request.header.Authorization",
        authorizerName: `${config.stack_name_base}-feedback-authorizer`,
      }
    )

    // Create /feedback resource and POST method
    const feedbackResource = api.root.addResource("feedback")
    feedbackResource.addMethod(
      "POST",
      new apigateway.LambdaIntegration(feedbackLambda),
      {
        authorizer,
        authorizationType: apigateway.AuthorizationType.COGNITO,
        requestValidator: requestValidator,
      }
    )

    // --- Patient Search endpoint (reuses this API + Cognito authorizer) ---
    const healthlakeRegion = config.backend?.healthlake?.region || cdk.Stack.of(this).region
    const healthlakeDatastoreId = config.backend?.healthlake?.datastore_id || ""

    const patientSearchLambda = new lambda.Function(this, "PatientSearchLambda", {
      functionName: `${config.stack_name_base}-patient-search`,
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: "index.handler",
      code: lambda.Code.fromAsset(path.join(__dirname, "..", "lambdas", "patient-search")),
      timeout: cdk.Duration.seconds(30),
      environment: {
        HEALTHLAKE_DATASTORE_ID: healthlakeDatastoreId,
        HEALTHLAKE_REGION: healthlakeRegion,
        CORS_ALLOWED_ORIGINS: `${frontendUrl},http://localhost:3000`,
      },
      logGroup: new logs.LogGroup(this, "PatientSearchLambdaLogGroup", {
        logGroupName: `/aws/lambda/${config.stack_name_base}-patient-search`,
        retention: logs.RetentionDays.ONE_WEEK,
        removalPolicy: cdk.RemovalPolicy.DESTROY,
      }),
    })

    // Allow the Lambda to read/search the HealthLake datastore
    patientSearchLambda.addToRolePolicy(
      new cdk.aws_iam.PolicyStatement({
        actions: [
          "healthlake:SearchWithGet",
          "healthlake:SearchWithPost",
          "healthlake:ReadResource",
        ],
        resources: [
          `arn:aws:healthlake:${healthlakeRegion}:${cdk.Stack.of(this).account}:datastore/fhir/${healthlakeDatastoreId}`,
        ],
      })
    )

    const patientsResource = api.root.addResource("patients")
    patientsResource.addMethod(
      "GET",
      new apigateway.LambdaIntegration(patientSearchLambda),
      {
        authorizer,
        authorizationType: apigateway.AuthorizationType.COGNITO,
      }
    )

    // --- Authorization write endpoint (user-initiated "Save Authorization") ---
    // The agent recommends a decision; a human clicks Save, which POSTs the
    // generated ClaimResponse here to persist it to HealthLake. Create-only,
    // restricted to ClaimResponse/Task, Cognito-authorized.
    const authorizationWriteLambda = new lambda.Function(this, "AuthorizationWriteLambda", {
      functionName: `${config.stack_name_base}-authorization-write`,
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: "index.handler",
      code: lambda.Code.fromAsset(path.join(__dirname, "..", "lambdas", "authorization-write")),
      timeout: cdk.Duration.seconds(30),
      environment: {
        HEALTHLAKE_DATASTORE_ID: healthlakeDatastoreId,
        HEALTHLAKE_REGION: healthlakeRegion,
        CORS_ALLOWED_ORIGINS: `${frontendUrl},http://localhost:3000`,
      },
      logGroup: new logs.LogGroup(this, "AuthorizationWriteLambdaLogGroup", {
        logGroupName: `/aws/lambda/${config.stack_name_base}-authorization-write`,
        retention: logs.RetentionDays.ONE_WEEK,
        removalPolicy: cdk.RemovalPolicy.DESTROY,
      }),
    })

    authorizationWriteLambda.addToRolePolicy(
      new cdk.aws_iam.PolicyStatement({
        actions: ["healthlake:CreateResource"],
        resources: [
          `arn:aws:healthlake:${healthlakeRegion}:${cdk.Stack.of(this).account}:datastore/fhir/${healthlakeDatastoreId}`,
        ],
      })
    )

    const authorizationsResource = api.root.addResource("authorizations")
    authorizationsResource.addMethod(
      "POST",
      new apigateway.LambdaIntegration(authorizationWriteLambda),
      {
        authorizer,
        authorizationType: apigateway.AuthorizationType.COGNITO,
      }
    )

    // Store feedback infrastructure info in SSM for backend stacks
    new ssm.StringParameter(this, "FeedbackTableNameParam", {
      parameterName: `/${config.stack_name_base}/feedback_table_name`,
      stringValue: feedbackTable.tableName,
      description: "Platform feedback DynamoDB table name",
    })

    new ssm.StringParameter(this, "FeedbackApiUrlParam", {
      parameterName: `/${config.stack_name_base}/feedback-api-url`,
      stringValue: api.url,
      description: "Platform feedback API Gateway URL",
    })

    // Outputs
    new cdk.CfnOutput(this, "PlatformFeedbackTableName", {
      value: feedbackTable.tableName,
      description: "Platform feedback table (shared by all patterns)",
      exportName: `${config.stack_name_base}-FeedbackTableName`,
    })

    new cdk.CfnOutput(this, "PlatformFeedbackApiUrl", {
      value: api.url,
      description: "Platform feedback API URL (shared by all patterns)",
      exportName: `${config.stack_name_base}-FeedbackApiUrl`,
    })
  }

  /**
   * Create a public CDS Hooks REST endpoint (CDS Hooks spec v1.0).
   *
   * Exposes:
   *   GET  /cds-services        → service discovery
   *   POST /cds-services/{id}   → invoke patient-view / order-select hooks
   *
   * SECURITY NOTE: This is an intentionally PUBLIC endpoint (no Cognito
   * authorizer) because CDS Hooks clients (EHRs, the CDS Hooks Sandbox)
   * authenticate with SMART/JWT bearer tokens, not Cognito. The Lambda
   * performs its own bearer-token check (dev mode requires the header to be
   * present; production verifies the JWT signature when CDS_HOOKS_REQUIRED_ISS,
   * CDS_HOOKS_REQUIRED_AUD and CDS_HOOKS_JWKS_URL are set). The discovery
   * endpoint is deliberately reachable without a token and returns a minimized
   * payload. Throttling is applied at the stage level to limit abuse.
   */
  private createCdsHooksApi(config: AppConfig, frontendUrl: string): void {
    const healthlakeRegion = config.backend?.healthlake?.region || cdk.Stack.of(this).region
    const healthlakeDatastoreId = config.backend?.healthlake?.datastore_id || ""
    const acct = cdk.Stack.of(this).account
    const region = cdk.Stack.of(this).region

    // --- Option 2: headless "run prior auth" behind a Lambda Function URL ---
    // Lets a CDS Hooks card trigger the full Prior Authorization Agent
    // end-to-end with NO browser login and NO multi-step UI. The agent takes
    // ~40-90s (over API Gateway's 29s cap), so a Function URL is used.
    // The endpoint is protected by a short-lived HMAC token that the CDS Hooks
    // Lambda mints into the card link (see _prior_auth_run_link).
    const priorAuthRunSecret = new secretsmanager.Secret(this, "PriorAuthRunSecret", {
      secretName: `/${config.stack_name_base}/prior-auth-run-hmac`,
      description: "HMAC secret used to sign prior-auth run links (Option 2)",
      generateSecretString: { passwordLength: 48, excludePunctuation: true },
    })

    const priorAuthRunJobs = new cdk.aws_dynamodb.Table(this, "PriorAuthRunJobs", {
      tableName: `${config.stack_name_base}-prior-auth-run-jobs`,
      partitionKey: { name: "jobId", type: cdk.aws_dynamodb.AttributeType.STRING },
      billingMode: cdk.aws_dynamodb.BillingMode.PAY_PER_REQUEST,
      timeToLiveAttribute: "ttl",
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    })

    const priorAuthRunLambda = new lambda.Function(this, "PriorAuthRunLambda", {
      functionName: `${config.stack_name_base}-prior-auth-run`,
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: "prior_auth_run_lambda.handler",
      code: lambda.Code.fromAsset(path.join(__dirname, "../../gateway/tools/prior_auth_run")),
      timeout: cdk.Duration.minutes(5),
      memorySize: 1024,
      environment: {
        STACK_NAME: config.stack_name_base,
        RUN_SECRET_ARN: priorAuthRunSecret.secretArn,
        JOBS_TABLE: priorAuthRunJobs.tableName,
      },
      logGroup: new logs.LogGroup(this, "PriorAuthRunLambdaLogGroup", {
        logGroupName: `/aws/lambda/${config.stack_name_base}-prior-auth-run`,
        retention: logs.RetentionDays.ONE_WEEK,
        removalPolicy: cdk.RemovalPolicy.DESTROY,
      }),
    })

    priorAuthRunSecret.grantRead(priorAuthRunLambda)

    // M2M token minting (SSM config + machine client secret) and runtime lookup
    priorAuthRunLambda.addToRolePolicy(
      new cdk.aws_iam.PolicyStatement({
        actions: ["ssm:GetParameter"],
        resources: [
          `arn:aws:ssm:${region}:${acct}:parameter/${config.stack_name_base}/cognito_provider`,
          `arn:aws:ssm:${region}:${acct}:parameter/${config.stack_name_base}/machine_client_id`,
          `arn:aws:ssm:${region}:${acct}:parameter/${config.stack_name_base}/prior-authorization-agent/runtime-arn`,
        ],
      })
    )
    priorAuthRunLambda.addToRolePolicy(
      new cdk.aws_iam.PolicyStatement({
        actions: ["secretsmanager:GetSecretValue"],
        resources: [
          `arn:aws:secretsmanager:${region}:${acct}:secret:/${config.stack_name_base}/machine_client_secret*`,
        ],
      })
    )

    // Async job store + permission for the start handler to self-invoke the
    // worker. Grant via a constructed ARN (not the function object) to avoid a
    // circular dependency between the function and its role policy.
    priorAuthRunJobs.grantReadWriteData(priorAuthRunLambda)
    priorAuthRunLambda.addToRolePolicy(
      new cdk.aws_iam.PolicyStatement({
        actions: ["lambda:InvokeFunction"],
        resources: [
          `arn:aws:lambda:${region}:${acct}:function:${config.stack_name_base}-prior-auth-run`,
        ],
      })
    )

    const cdsHooksLambda = new lambda.Function(this, "CdsHooksLambda", {
      functionName: `${config.stack_name_base}-cds-hooks`,
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: "cds_hooks_lambda.handler",
      code: lambda.Code.fromAsset(path.join(__dirname, "../../gateway/tools/cds_hooks")),
      timeout: cdk.Duration.seconds(30),
      memorySize: 256,
      environment: {
        HEALTHLAKE_DATASTORE_ID: healthlakeDatastoreId,
        HEALTHLAKE_REGION: healthlakeRegion,
        // Explicit CORS allowlist (no wildcard). Includes the public CDS Hooks Sandbox.
        CDS_HOOKS_ALLOWED_ORIGINS: `${frontendUrl},http://localhost:3000,https://sandbox.cds-hooks.org`,
        // Canonical prior-auth requirement rule source (single source of truth,
        // shared with the Prior Auth Agent). order-select delegates to it.
        PAYOR_POLICY_LAMBDA_NAME: this.payorPolicyLambda.functionName,
        // Deep-link target so the EHR card routes to the agent-backed assessment.
        APP_URL: frontendUrl,
        // Option 2 HMAC secret to sign card links; the run URL is set below
        // once the public API Gateway route exists (addEnvironment).
        RUN_SECRET_ARN: priorAuthRunSecret.secretArn,
      },
      logGroup: new logs.LogGroup(this, "CdsHooksLambdaLogGroup", {
        logGroupName: `/aws/lambda/${config.stack_name_base}-cds-hooks`,
        retention: logs.RetentionDays.ONE_WEEK,
        removalPolicy: cdk.RemovalPolicy.DESTROY,
      }),
    })

    // Allow CDS order-select to invoke the canonical payor-policy rule Lambda
    this.payorPolicyLambda.grantInvoke(cdsHooksLambda)

    // Allow the CDS Hooks Lambda to read the HMAC secret so it can sign the
    // Option 2 "run prior auth" card links.
    priorAuthRunSecret.grantRead(cdsHooksLambda)

    // Allow the Lambda to read/search the HealthLake datastore (FHIR R4)
    cdsHooksLambda.addToRolePolicy(
      new cdk.aws_iam.PolicyStatement({
        actions: [
          "healthlake:SearchWithGet",
          "healthlake:SearchWithPost",
          "healthlake:ReadResource",
        ],
        resources: [
          `arn:aws:healthlake:${healthlakeRegion}:${cdk.Stack.of(this).account}:datastore/fhir/${healthlakeDatastoreId}`,
        ],
      })
    )

    // Dedicated public REST API for CDS Hooks (no Cognito authorizer)
    const cdsApi = new apigateway.RestApi(this, "CdsHooksApi", {
      restApiName: `${config.stack_name_base}-cds-hooks-api`,
      description: "Public CDS Hooks endpoint (discovery + patient-view/order-select)",
      defaultCorsPreflightOptions: {
        // CDS Hooks discovery is a public endpoint; allow any origin for preflight.
        allowOrigins: apigateway.Cors.ALL_ORIGINS,
        allowMethods: ["GET", "POST", "OPTIONS"],
        allowHeaders: ["Content-Type", "Authorization"],
      },
      deployOptions: {
        stageName: "prod",
        throttlingRateLimit: 50,
        throttlingBurstLimit: 100,
        loggingLevel: apigateway.MethodLoggingLevel.INFO,
        metricsEnabled: true,
        accessLogDestination: new apigateway.LogGroupLogDestination(
          new logs.LogGroup(this, "CdsHooksApiAccessLogGroup", {
            logGroupName: `/aws/apigateway/${config.stack_name_base}-cds-hooks-api-access`,
            retention: logs.RetentionDays.ONE_WEEK,
            removalPolicy: cdk.RemovalPolicy.DESTROY,
          })
        ),
        accessLogFormat: apigateway.AccessLogFormat.jsonWithStandardFields(),
        tracingEnabled: true,
      },
    })

    const integration = new apigateway.LambdaIntegration(cdsHooksLambda)

    // GET /cds-services  → discovery
    const cdsServices = cdsApi.root.addResource("cds-services")
    cdsServices.addMethod("GET", integration)

    // POST /cds-services/{id}  → hook invocation (patient-view / order-select)
    const cdsServiceById = cdsServices.addResource("{id}")
    cdsServiceById.addMethod("POST", integration)

    // Option 2: GET /prior-auth-run → start (HMAC-verified) or poll (jobId) the
    // headless Prior Auth Agent. Public (like discovery); the agent run itself
    // is gated by the short-lived HMAC token minted into the card link.
    const priorAuthRunResource = cdsApi.root.addResource("prior-auth-run")
    priorAuthRunResource.addMethod("GET", new apigateway.LambdaIntegration(priorAuthRunLambda))

    // Now that the public route exists, give the CDS Hooks Lambda the run URL so
    // it can build the card's "Submit Prior Authorization" link. Construct the
    // URL from restApiId + stage (not cdsApi.url) to avoid a circular dependency
    // (the API's methods already depend on this Lambda).
    cdsHooksLambda.addEnvironment(
      "PRIOR_AUTH_RUN_URL",
      `https://${cdsApi.restApiId}.execute-api.${region}.amazonaws.com/prod/prior-auth-run`
    )

    new ssm.StringParameter(this, "CdsHooksApiUrlParam", {
      parameterName: `/${config.stack_name_base}/cds-hooks-api-url`,
      stringValue: cdsApi.url,
      description: "Public CDS Hooks API Gateway URL",
    })

    new cdk.CfnOutput(this, "CdsHooksApiUrl", {
      value: cdsApi.url,
      description: "Public CDS Hooks API URL (discovery: GET {url}cds-services)",
      exportName: `${config.stack_name_base}-CdsHooksApiUrl`,
    })

    new cdk.CfnOutput(this, "PriorAuthRunUrl", {
      value: `https://${cdsApi.restApiId}.execute-api.${region}.amazonaws.com/prod/prior-auth-run`,
      description: "Option 2 headless prior-auth agent endpoint (HMAC-signed links, async)",
      exportName: `${config.stack_name_base}-PriorAuthRunUrl`,
    })
  }

  private createLangfuseSecret(config: AppConfig): void {
    // Create shared Langfuse secret for observability (used by all agent patterns)
    // Read from .env at deployment time, store securely in Secrets Manager
    const langfuseSecretKey = process.env.LANGFUSE_SECRET_KEY || ""
    const langfusePublicKey = process.env.LANGFUSE_PUBLIC_KEY || ""
    const langfuseBaseUrl = process.env.LANGFUSE_BASE_URL || ""

    const langfuseSecret = new secretsmanager.Secret(this, "SharedLangfuseSecret", {
      secretName: `/${config.stack_name_base}/langfuse/credentials`,
      description: "Langfuse API credentials for observability (shared by all patterns)",
      secretObjectValue: {
        publicKey: cdk.SecretValue.unsafePlainText(langfusePublicKey),
        secretKey: cdk.SecretValue.unsafePlainText(langfuseSecretKey),
        baseUrl: cdk.SecretValue.unsafePlainText(langfuseBaseUrl),
      },
    })

    // Output
    new cdk.CfnOutput(this, "LangfuseSecretArn", {
      value: langfuseSecret.secretArn,
      description: "Langfuse secret ARN (shared by all patterns)",
      exportName: `${config.stack_name_base}-LangfuseSecretArn`,
    })
  }

  private createPhiGuardrail(config: AppConfig): void {
    // Bedrock Guardrail to redact PHI from observability traces (HIPAA compliance)
    const guardrail = new cdk.aws_bedrock.CfnGuardrail(this, "PhiMaskingGuardrail", {
      name: `${config.stack_name_base}-phi-masking`,
      description: "Redacts PHI (names, SSN, DOB, MRN, phone, email, address) from observability traces",
      blockedInputMessaging: "[PHI REDACTED]",
      blockedOutputsMessaging: "[PHI REDACTED]",
      sensitiveInformationPolicyConfig: {
        piiEntitiesConfig: [
          { type: "NAME",          action: "ANONYMIZE" },
          { type: "EMAIL",         action: "ANONYMIZE" },
          { type: "PHONE",         action: "ANONYMIZE" },
          { type: "US_SOCIAL_SECURITY_NUMBER", action: "ANONYMIZE" },
          { type: "US_INDIVIDUAL_TAX_IDENTIFICATION_NUMBER", action: "ANONYMIZE" },
          { type: "ADDRESS",       action: "ANONYMIZE" },
          { type: "DRIVER_ID",     action: "ANONYMIZE" },
          { type: "LICENSE_PLATE", action: "ANONYMIZE" },
          { type: "VEHICLE_IDENTIFICATION_NUMBER", action: "ANONYMIZE" },
          { type: "IP_ADDRESS",    action: "ANONYMIZE" },
          { type: "URL",           action: "ANONYMIZE" },
          { type: "AWS_ACCESS_KEY", action: "ANONYMIZE" },
          { type: "AWS_SECRET_KEY", action: "ANONYMIZE" },
        ],
        // 10 regex slots max (Bedrock quota). Fax covered by PHONE PII type.
        // Written-month dates + fax handled by regex second-pass in observability.py.
        regexesConfig: [
          // Dates: DOB, admission, discharge, death with contextual label (HIPAA #3)
          {
            name: "Date_With_Label",
            description: "Dates preceded by DOB, admission, discharge, death labels",
            pattern: "(?i)\\b(DOB|date of birth|birthdate|birth date|admission date|discharge date|date of death|DOD|DOA)[:\\s]+\\d{1,2}[/\\-]\\d{1,2}[/\\-]\\d{2,4}\\b",
            action: "ANONYMIZE",
          },
          // Bare mm/dd/yyyy dates (HIPAA #3)
          {
            name: "Date_MMDDYYYY",
            description: "Dates in MM/DD/YYYY or MM-DD-YYYY format",
            pattern: "\\b(0?[1-9]|1[0-2])[/\\-](0?[1-9]|[12]\\d|3[01])[/\\-](\\d{2}|\\d{4})\\b",
            action: "ANONYMIZE",
          },
          // Ages over 89 (HIPAA #3)
          {
            name: "Age_Over_89",
            description: "Ages 90 and above",
            pattern: "(?i)\\b(9\\d|1[0-9]\\d)[-\\s]?year[-\\s]?old\\b",
            action: "ANONYMIZE",
          },
          // Medical Record Numbers (HIPAA #8)
          {
            name: "MRN",
            description: "Medical Record Numbers with label prefix",
            pattern: "(?i)\\b(MRN|Medical Record( Number)?|Chart (Number|#))[:\\s#]+[\\w\\-]+\\b",
            action: "ANONYMIZE",
          },
          // Health plan beneficiary numbers (HIPAA #9)
          {
            name: "Health_Plan_Beneficiary",
            description: "Health plan beneficiary, member, or policy numbers",
            pattern: "(?i)\\b(beneficiary( (number|#|id))?|member (id|#)|plan (id|#)|policy (number|#))[:\\s#]+[\\w\\-]+\\b",
            action: "ANONYMIZE",
          },
          // Account numbers (HIPAA #10)
          {
            name: "Account_Number",
            description: "Account numbers with label prefix",
            pattern: "(?i)\\b(account (number|#|no\\.?)|acct)[:\\s#]+[\\w\\-]+\\b",
            action: "ANONYMIZE",
          },
          // Certificate / license numbers (HIPAA #11)
          {
            name: "License_Certificate_Number",
            description: "License and certificate numbers with label prefix",
            pattern: "(?i)\\b(license (number|#|no\\.?)|certificate (number|#)|cert)[:\\s#]+[\\w\\-]+\\b",
            action: "ANONYMIZE",
          },
          // Device identifiers and serial numbers (HIPAA #13)
          {
            name: "Device_Serial_Number",
            description: "Device identifiers and serial numbers",
            pattern: "(?i)\\b(serial (number|#|no\\.?)|device (id|#)|s/n)[:\\s#]+[\\w\\-]+\\b",
            action: "ANONYMIZE",
          },
          // NPI — National Provider Identifier (10 digits)
          {
            name: "NPI",
            description: "National Provider Identifier (10-digit)",
            pattern: "(?i)\\bNPI[:\\s]+\\d{10}\\b",
            action: "ANONYMIZE",
          },
          // ZIP codes with label (HIPAA #2)
          {
            name: "ZIP_Code",
            description: "ZIP codes preceded by ZIP/postal code label",
            pattern: "(?i)\\b(ZIP|zip code|postal code)[:\\s]+\\d{5}(\\-\\d{4})?\\b",
            action: "ANONYMIZE",
          },
        ],
      },
    })

    // Store Guardrail ID and version in SSM for runtime lookup
    new ssm.StringParameter(this, "PhiGuardrailIdParam", {
      parameterName: `/${config.stack_name_base}/phi-guardrail-id`,
      stringValue: guardrail.attrGuardrailId,
      description: "Bedrock Guardrail ID for PHI masking in observability traces",
    })

    new ssm.StringParameter(this, "PhiGuardrailVersionParam", {
      parameterName: `/${config.stack_name_base}/phi-guardrail-version`,
      stringValue: "DRAFT",
      description: "Bedrock Guardrail version for PHI masking",
    })

    new cdk.CfnOutput(this, "PhiGuardrailId", {
      value: guardrail.attrGuardrailId,
      description: "Bedrock Guardrail ID for PHI masking",
    })
  }

  private createCognitoSSMParameters(config: AppConfig): void {
    // Create shared Cognito SSM parameters (used by all agent patterns)
    // These are the same for all patterns since they all use the same Cognito pool

    new ssm.StringParameter(this, "CognitoUserPoolIdParam", {
      parameterName: `/${config.stack_name_base}/cognito-user-pool-id`,
      stringValue: this.cognitoStack.userPoolId,
      description: "Shared Cognito User Pool ID (used by all patterns)",
    })

    new ssm.StringParameter(this, "CognitoUserPoolClientIdParam", {
      parameterName: `/${config.stack_name_base}/cognito-user-pool-client-id`,
      stringValue: this.cognitoStack.userPoolClientId,
      description: "Shared Cognito User Pool Client ID (used by all patterns)",
    })

    new ssm.StringParameter(this, "CognitoDomainParam", {
      parameterName: `/${config.stack_name_base}/cognito_provider`,
      stringValue: `${this.cognitoStack.userPoolDomain.domainName}.auth.${cdk.Aws.REGION}.amazoncognito.com`,
      description: "Shared Cognito domain URL for token endpoint (used by all patterns)",
    })

    new ssm.StringParameter(this, "GatewayUrlParam", {
      parameterName: `/${config.stack_name_base}/gateway_url`,
      stringValue: this.sharedGateway.attrGatewayUrl,
      description: "Shared Gateway URL (used by all patterns)",
    })
  }
}
