// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

"use client";

import { useEffect, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { useAuth } from "@/hooks/useAuth";

/**
 * OAuth 2.0 Callback Handler for Epic FHIR USER_FEDERATION
 *
 * This page handles the OAuth callback from AgentCore Identity after the user
 * authorizes access to their Epic FHIR data. It:
 * 1. Extracts the session_id from query parameters
 * 2. Validates the current user session
 * 3. Calls CompleteResourceTokenAuth API to complete the OAuth flow
 * 4. Redirects back to the clinical decision support agent
 */
export default function OAuthCallbackPage() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const { user, isAuthenticated, isLoading } = useAuth();
  const [status, setStatus] = useState<"processing" | "success" | "error">("processing");
  const [message, setMessage] = useState("Processing OAuth authorization...");

  useEffect(() => {
    async function handleCallback() {
      try {
        // Wait for auth to load
        if (isLoading) {
          return;
        }

        // Extract session_id from query parameters
        const sessionId = searchParams.get("session_id");

        if (!sessionId) {
          setStatus("error");
          setMessage("Missing session_id parameter");
          console.error("OAuth callback missing session_id");
          return;
        }

        // Validate user session
        if (!isAuthenticated || !user?.profile?.sub) {
          setStatus("error");
          setMessage("User session not found. Please log in.");
          console.error("OAuth callback - no user session");
          return;
        }

        const userId = user.profile.sub;
        const accessToken = user.access_token;

        if (!accessToken) {
          throw new Error("No access token found. Please log in again.");
        }

        console.log(`[OAuth Callback] Completing auth for user: ${userId}, session: ${sessionId}`);

        // Call CompleteResourceTokenAuth API
        const region = "us-east-1"; // TODO: Get from config
        const response = await fetch(
          `https://bedrock-agentcore.${region}.amazonaws.com/identities/complete-resource-token-auth`,
          {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "Authorization": `Bearer ${accessToken}`,
            },
            body: JSON.stringify({
              sessionUri: sessionId,
              userIdentifier: {
                userId: userId, // Cognito user ID
              },
            }),
          }
        );

        if (!response.ok) {
          const errorData = await response.json().catch(() => ({}));
          throw new Error(
            `CompleteResourceTokenAuth failed: ${response.status} ${JSON.stringify(errorData)}`
          );
        }

        console.log("[OAuth Callback] Successfully completed authorization");
        setStatus("success");
        setMessage("Authorization successful! Redirecting...");

        // If opened as popup, notify parent window
        if (window.opener && !window.opener.closed) {
          console.log("[OAuth Callback] Notifying parent window");
          window.opener.postMessage({ type: 'oauth_complete', sessionId }, window.location.origin);
          // Close popup after notifying parent
          setTimeout(() => {
            window.close();
          }, 1000);
        } else {
          // If not a popup, redirect back to clinical decision support agent
          setTimeout(() => {
            router.push("/clinical-decision-support");
          }, 2000);
        }
      } catch (error) {
        console.error("[OAuth Callback] Error:", error);
        setStatus("error");
        setMessage(
          error instanceof Error
            ? `Error: ${error.message}`
            : "An unexpected error occurred"
        );
      }
    }

    handleCallback();
  }, [searchParams, user, isAuthenticated, isLoading, router]);

  return (
    <div style={{
      display: "flex",
      flexDirection: "column",
      alignItems: "center",
      justifyContent: "center",
      minHeight: "100vh",
      padding: "20px",
      backgroundColor: "#f5f5f5",
    }}>
      <div style={{
        backgroundColor: "white",
        padding: "40px",
        borderRadius: "8px",
        boxShadow: "0 2px 10px rgba(0,0,0,0.1)",
        maxWidth: "500px",
        textAlign: "center",
      }}>
        {status === "processing" && (
          <>
            <div style={{
              width: "50px",
              height: "50px",
              border: "4px solid #f3f3f3",
              borderTop: "4px solid #3498db",
              borderRadius: "50%",
              animation: "spin 1s linear infinite",
              margin: "0 auto 20px",
            }} />
            <h2 style={{ marginBottom: "10px", color: "#333" }}>Processing Authorization</h2>
          </>
        )}

        {status === "success" && (
          <>
            <div style={{
              fontSize: "50px",
              marginBottom: "20px",
            }}>✓</div>
            <h2 style={{ marginBottom: "10px", color: "#27ae60" }}>Success!</h2>
          </>
        )}

        {status === "error" && (
          <>
            <div style={{
              fontSize: "50px",
              marginBottom: "20px",
            }}>✗</div>
            <h2 style={{ marginBottom: "10px", color: "#e74c3c" }}>Error</h2>
          </>
        )}

        <p style={{ color: "#666", marginBottom: "20px" }}>{message}</p>

        {status === "error" && (
          <button
            onClick={() => router.push("/clinical-decision-support")}
            style={{
              padding: "10px 20px",
              backgroundColor: "#3498db",
              color: "white",
              border: "none",
              borderRadius: "4px",
              cursor: "pointer",
            }}
          >
            Return to Agent
          </button>
        )}
      </div>

      <style jsx>{`
        @keyframes spin {
          0% { transform: rotate(0deg); }
          100% { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
}
