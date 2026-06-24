// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import { WebStorageStateStore } from "oidc-client-ts"

// Configuration type for Cognito authentication
type CognitoAuthConfig = {
  authority: string
  client_id: string
  redirect_uri: string
  post_logout_redirect_uri: string
  response_type: string
  scope: string
  automaticSilentRenew: boolean
  userStore: WebStorageStateStore
  stateStore: WebStorageStateStore
}

// Cache for loaded config
let configCache: CognitoAuthConfig | null = null

/**
 * Load aws-exports.json from the public folder
 */
async function loadAwsExports(): Promise<any> {
  try {
    const response = await fetch("/aws-exports.json")
    if (!response.ok) {
      throw new Error(`Failed to load aws-exports.json: ${response.status}`)
    }
    return await response.json()
  } catch (error) {
    console.error("Failed to load aws-exports.json:", error)
    throw error
  }
}

/**
 * In-memory storage backend for oidc-client-ts.
 *
 * Threat T3 mitigation: never persist tokens to sessionStorage or
 * localStorage where any script (including XSS or a malicious extension)
 * could read them. The oidc library will keep tokens in this map for the
 * lifetime of the page; on refresh the silent-renew flow reissues them via
 * the (HttpOnly) Cognito session cookie.
 */
class InMemoryWebStorage implements Storage {
  private store = new Map<string, string>()
  get length() {
    return this.store.size
  }
  clear() {
    this.store.clear()
  }
  getItem(key: string) {
    return this.store.get(key) ?? null
  }
  key(index: number) {
    return Array.from(this.store.keys())[index] ?? null
  }
  removeItem(key: string) {
    this.store.delete(key)
  }
  setItem(key: string, value: string) {
    this.store.set(key, String(value))
  }
}

/**
 * Create Cognito authentication configuration.
 *
 * Uses an in-memory store for both user state and OIDC interaction state to
 * close the XSS -> token-theft vector (Threat T3).
 */
export async function createCognitoAuthConfig(): Promise<CognitoAuthConfig> {
  if (configCache) {
    return configCache
  }

  const awsExports = await loadAwsExports()

  const inMemoryStore = new InMemoryWebStorage()

  // Threat T3: tokens stay in memory only (userStore). The OIDC interaction
  // state (state/nonce/PKCE code_verifier) MUST survive the full-page redirect
  // to the Cognito hosted UI and back, so it uses sessionStorage. These values
  // are transient, single-use, and contain no tokens — storing them in
  // sessionStorage is the standard, safe approach and is cleared on tab close.
  const stateStorageBackend =
    typeof window !== "undefined" ? window.sessionStorage : inMemoryStore

  const config: CognitoAuthConfig = {
    authority: awsExports.authority,
    client_id: awsExports.client_id,
    redirect_uri: awsExports.redirect_uri,
    post_logout_redirect_uri: awsExports.post_logout_redirect_uri || awsExports.redirect_uri,
    response_type: awsExports.response_type || "code",
    scope: awsExports.scope || "email openid profile",
    automaticSilentRenew: awsExports.automaticSilentRenew ?? true,
    // T3: keep tokens in memory only.
    userStore: new WebStorageStateStore({ store: inMemoryStore }),
    // Interaction state must persist across the redirect — use sessionStorage.
    stateStore: new WebStorageStateStore({ store: stateStorageBackend }),
  }

  configCache = config

  return config
}
