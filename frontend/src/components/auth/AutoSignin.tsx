"use client"

import { ReactNode, useEffect, useState, PropsWithChildren } from "react"
import { useAuth } from "react-oidc-context"
import { useRouter } from "next/navigation"
import { Button } from "@/components/ui/button"

// Key used to carry the intended deep-link (e.g. a CDS Hooks
// /orders/prior-auth?patientId=... link) across the Cognito login redirect.
const POST_LOGIN_REDIRECT_KEY = "postLoginRedirect"

function captureDeepLink() {
  if (typeof window === "undefined") return
  const dest = window.location.pathname + window.location.search
  // Only worth restoring non-trivial deep links (a route with query params).
  if (window.location.search && dest !== "/") {
    try { window.sessionStorage.setItem(POST_LOGIN_REDIRECT_KEY, dest) } catch { /* ignore */ }
  }
}

function AutoSigninContent({ children }: PropsWithChildren) {
  const auth = useAuth()
  const router = useRouter()

  // Before redirecting to Cognito, remember where the user was headed.
  useEffect(() => {
    if (!auth.isLoading && !auth.isAuthenticated && !auth.error) {
      captureDeepLink()
    }
  }, [auth.isLoading, auth.isAuthenticated, auth.error])

  // After authentication, restore the captured deep-link via client-side
  // navigation (a full reload would drop the in-memory tokens — Threat T3).
  useEffect(() => {
    if (!auth.isAuthenticated) return
    let dest: string | null = null
    try { dest = window.sessionStorage.getItem(POST_LOGIN_REDIRECT_KEY) } catch { /* ignore */ }
    if (!dest) return
    try { window.sessionStorage.removeItem(POST_LOGIN_REDIRECT_KEY) } catch { /* ignore */ }
    const current = window.location.pathname + window.location.search
    if (dest !== current) router.replace(dest)
  }, [auth.isAuthenticated, router])

  if (auth.isLoading) {
    return <div className="flex items-center justify-center min-h-screen text-xl">Loading...</div>
  }

  if (auth.error) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen gap-4">
        <p className="text-xl text-red-600">Authentication Error</p>
        <p className="text-sm text-gray-600">{auth.error.message}</p>
        <Button onClick={() => window.location.reload()}>Reload</Button>
      </div>
    )
  }

  if (!auth.isAuthenticated) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen gap-4">
        <p className="text-4xl">Please sign in</p>
        <Button
          onClick={() => {
            // Capture the deep-link, then trigger the OAuth login flow.
            captureDeepLink()
            auth.signinRedirect()
          }}
        >
          Sign In
        </Button>
      </div>
    )
  }

  return <>{children}</>
}

export function AutoSignin({ children }: { children: ReactNode }) {
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    setMounted(true)
  }, [])

  if (!mounted) {
    return null
  }

  return <AutoSigninContent>{children}</AutoSigninContent>
}
