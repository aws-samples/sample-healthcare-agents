// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
//
// Threat T3 mitigation:
// Single hook to retrieve the current access token + Cognito sub from the
// react-oidc-context library, which (per src/lib/auth.ts) stores them in
// memory only. Components MUST use this hook instead of reading
// `sessionStorage.getItem('oidc.user:*')` directly.

"use client"

import { useAuth } from "react-oidc-context"

export type AuthToken = {
  accessToken: string | null
  idToken: string | null
  userId: string | null
  isAuthenticated: boolean
}

export function useAuthToken(): AuthToken {
  const auth = useAuth()
  return {
    accessToken: auth.user?.access_token ?? null,
    idToken: auth.user?.id_token ?? null,
    userId: auth.user?.profile?.sub ?? null,
    isAuthenticated: !!auth.isAuthenticated,
  }
}
