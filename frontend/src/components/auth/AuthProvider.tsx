"use client"

import { createCognitoAuthConfig } from "@/lib/auth"
import { useEffect, useState, PropsWithChildren } from "react"
import { AuthProvider as OidcAuthProvider, AuthProviderProps } from "react-oidc-context"
import { AutoSignin } from "./AutoSignin"

const AuthProvider = ({ children }: PropsWithChildren) => {
  const [authConfig, setAuthConfig] = useState<AuthProviderProps | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    async function loadConfig() {
      try {
        const config = await createCognitoAuthConfig()
        setAuthConfig(config as AuthProviderProps)
      } catch (err) {
        console.error("Failed to load auth configuration:", err)
        setError("Failed to load authentication configuration")
      } finally {
        setLoading(false)
      }
    }

    loadConfig()
  }, [])

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen text-xl">
        Loading authentication...
      </div>
    )
  }

  if (error || !authConfig) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen gap-4">
        <p className="text-xl text-red-600">{error || "Authentication configuration error"}</p>
        <p className="text-sm text-gray-600">Please check the console for details</p>
      </div>
    )
  }

  return (
    <OidcAuthProvider
      {...authConfig}
      onSigninCallback={() => {
        // Clean up URL after OAuth callback
        window.history.replaceState({}, document.title, window.location.pathname)
      }}
      // Ensure we handle errors gracefully
      onRemoveUser={() => {
        // Clear any stale state
        console.log("User removed from OIDC context")
      }}
    >
      <AutoSignin>{children}</AutoSignin>
    </OidcAuthProvider>
  )
}

export { AuthProvider }
