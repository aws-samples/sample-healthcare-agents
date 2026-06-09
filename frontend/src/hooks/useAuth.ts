"use client"

import { useAuth as useOidcAuth } from "react-oidc-context"

export function useAuth() {
  const auth = useOidcAuth()

  // If no AuthProvider context, return mock auth state (for development without auth)
  if (!auth) {
    return {
      isAuthenticated: false,
      user: null,
      signIn: () => {},
      signOut: () => {},
      isLoading: false,
      error: null,
      token: null,
    }
  }

  return {
    isAuthenticated: auth.isAuthenticated,
    user: auth.user,
    signIn: auth.signinRedirect,
    signOut: () => {
      auth.signoutRedirect()
    },
    isLoading: auth.isLoading,
    error: auth.error,
    token: auth.user?.id_token,
  }
}
