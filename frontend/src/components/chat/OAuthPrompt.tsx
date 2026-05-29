// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import { OAuthElicitation } from "./types"
import { Button } from "@/components/ui/button"

interface OAuthPromptProps {
  elicitation: OAuthElicitation
  sessionId: string
}

export function OAuthPrompt({ elicitation, sessionId }: OAuthPromptProps) {
  const handleAuthorize = () => {
    // Build the authorization URL with session_id parameter
    const authUrl = new URL(elicitation.authorizationUrl)
    authUrl.searchParams.set('session_id', sessionId)

    // Open authorization in a popup window
    const width = 600
    const height = 700
    const left = window.screen.width / 2 - width / 2
    const top = window.screen.height / 2 - height / 2

    const popup = window.open(
      authUrl.toString(),
      'oauth_popup',
      `width=${width},height=${height},left=${left},top=${top},toolbar=no,menubar=no,scrollbars=yes,resizable=yes`
    )

    // Listen for messages from the popup
    const messageHandler = (event: MessageEvent) => {
      // Validate origin to prevent cross-origin XSS attacks
      if (event.origin !== window.location.origin) {
        console.warn('[OAuth] Ignored message from unexpected origin:', event.origin)
        return
      }
      if (event.data?.type === 'oauth_complete') {
        console.log('[OAuth] Authorization completed')
        popup?.close()
        window.removeEventListener('message', messageHandler)
        // Parent component will handle re-invoking the agent
        window.location.reload() // Simple approach: reload to retry
      }
    }

    window.addEventListener('message', messageHandler)

    // Cleanup if popup is closed manually
    const checkPopup = setInterval(() => {
      if (popup?.closed) {
        clearInterval(checkPopup)
        window.removeEventListener('message', messageHandler)
      }
    }, 500)
  }

  return (
    <div className="border border-blue-200 bg-blue-50 rounded-lg p-4 my-2">
      <div className="flex items-start gap-3">
        <div className="flex-shrink-0">
          <svg
            className="w-6 h-6 text-blue-600"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
            />
          </svg>
        </div>
        <div className="flex-1">
          <h3 className="text-sm font-semibold text-blue-900 mb-1">
            Authorization Required
          </h3>
          <p className="text-sm text-blue-800 mb-3">
            This action requires authorization to access {elicitation.resourceType || 'external resources'}.
            {elicitation.scopes && elicitation.scopes.length > 0 && (
              <span className="block mt-1 text-xs text-blue-700">
                Permissions: {elicitation.scopes.join(', ')}
              </span>
            )}
          </p>
          <Button
            onClick={handleAuthorize}
            className="bg-blue-600 hover:bg-blue-700 text-white text-sm"
          >
            Authorize Access
          </Button>
        </div>
      </div>
    </div>
  )
}
