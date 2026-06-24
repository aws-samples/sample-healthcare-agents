import * as fs from "fs"
import * as path from "path"
import * as yaml from "yaml"

const MAX_STACK_NAME_BASE_LENGTH = 35

export type DeploymentType = "docker" | "zip"

export interface PatternConfig {
  pattern: string
  deployment_type: DeploymentType
  enabled?: boolean
}

export interface AppConfig {
  stack_name_base: string
  admin_user_email?: string | null
  backend: {
    // Legacy single pattern support (deprecated)
    pattern?: string
    deployment_type?: DeploymentType
    // New multi-pattern support
    patterns?: PatternConfig[]
    healthlake?: {
      read_only_mode?: boolean
      region?: string
      datastore_id?: string
    }
  }
}

export class ConfigManager {
  private config: AppConfig

  constructor(configFile: string) {
    this.config = this._loadConfig(configFile)
  }

  private _loadConfig(configFile: string): AppConfig {
    const configPath = path.join(__dirname, "..", "..", configFile)

    if (!fs.existsSync(configPath)) {
      throw new Error(`Configuration file ${configPath} does not exist. Please create config.yaml file.`)
    }

    try {
      const fileContent = fs.readFileSync(configPath, "utf8")
      const parsedConfig = yaml.parse(fileContent) as AppConfig

      const deploymentType = parsedConfig.backend?.deployment_type || "docker"
      if (deploymentType !== "docker" && deploymentType !== "zip") {
        throw new Error(`Invalid deployment_type '${deploymentType}'. Must be 'docker' or 'zip'.`)
      }

      const stackNameBase = parsedConfig.stack_name_base
      if (!stackNameBase) {
        throw new Error("stack_name_base is required in config.yaml")
      }
      if (stackNameBase.length > MAX_STACK_NAME_BASE_LENGTH) {
        throw new Error(
          `stack_name_base '${stackNameBase}' is too long (${stackNameBase.length} chars). ` +
            `Maximum length is ${MAX_STACK_NAME_BASE_LENGTH} characters due to AWS AgentCore runtime naming constraints.`
        )
      }

      // Support both legacy single pattern and new multi-pattern configuration
      let patterns: PatternConfig[] = []

      if (parsedConfig.backend?.patterns && Array.isArray(parsedConfig.backend.patterns)) {
        // New multi-pattern configuration
        patterns = parsedConfig.backend.patterns.filter(p => p.enabled !== false)
      } else if (parsedConfig.backend?.pattern) {
        // Legacy single pattern configuration - convert to new format
        patterns = [{
          pattern: parsedConfig.backend.pattern,
          deployment_type: deploymentType,
          enabled: true
        }]
      }

      if (patterns.length === 0) {
        throw new Error("No enabled patterns found in backend configuration")
      }

      return {
        stack_name_base: stackNameBase,
        admin_user_email: parsedConfig.admin_user_email || null,
        backend: {
          // Keep legacy fields for backward compatibility
          pattern: parsedConfig.backend?.pattern,
          deployment_type: deploymentType,
          // New multi-pattern support
          patterns: patterns,
          // Allow a deploy-time override of the HealthLake datastore ID via the
          // HEALTHLAKE_DATASTORE_ID env var, so the real ID never has to be
          // committed to config.yaml (which keeps a placeholder for the public
          // repo). Falls back to whatever is in config.yaml.
          healthlake: parsedConfig.backend?.healthlake
            ? {
                ...parsedConfig.backend.healthlake,
                datastore_id:
                  process.env.HEALTHLAKE_DATASTORE_ID ||
                  parsedConfig.backend.healthlake.datastore_id,
              }
            : process.env.HEALTHLAKE_DATASTORE_ID
              ? { datastore_id: process.env.HEALTHLAKE_DATASTORE_ID }
              : undefined,
        },
      }
    } catch (error) {
      throw new Error(`Failed to parse configuration file ${configPath}: ${error}`)
    }
  }

  public getProps(): AppConfig {
    return this.config
  }

  public getEnabledPatterns(): PatternConfig[] {
    return this.config.backend.patterns || []
  }

  public get(key: string, defaultValue?: any): any {
    const keys = key.split(".")
    let value: any = this.config

    for (const k of keys) {
      if (typeof value === "object" && value !== null && k in value) {
        value = value[k]
      } else {
        return defaultValue
      }
    }

    return value
  }
}
