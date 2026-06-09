// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

"use client"

import React, { useEffect, useState } from "react"
import ChatInterface from "@/components/chat/ChatInterface"
import { Button } from "@/components/ui/button"
import { useAuth } from "@/hooks/useAuth"
import { GlobalContextProvider } from "@/app/context/GlobalContext"
import { setAgentConfig } from "@/services/agentCoreService"

export default function ClinicalDecisionSupportPage() {
  const { isAuthenticated, signIn } = useAuth()
  const [configLoaded, setConfigLoaded] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    async function loadConfig() {
      try {
        const response = await fetch("/aws-exports.json")
        if (!response.ok) {
          throw new Error("Failed to load configuration")
        }
        const config = await response.json()

        // Get clinical-decision-agent-langgraph config (new LangGraph runtime)
        const agentConfig = config.agents?.["clinical-decision-agent-langgraph"]
        if (!agentConfig || !agentConfig.runtimeArn) {
          throw new Error("Clinical Decision Support agent not found in configuration")
        }

        // Use the agentPattern from config, defaulting to langgraph-single-agent
        await setAgentConfig(
          agentConfig.runtimeArn,
          agentConfig.region || config.awsRegion || "us-east-1",
          agentConfig.agentPattern || "langgraph-single-agent"
        )
        setConfigLoaded(true)
      } catch (err) {
        const errorMessage = err instanceof Error ? err.message : "Unknown error"
        setError(`Configuration error: ${errorMessage}`)
        console.error("Failed to load agent configuration:", err)
      }
    }

    if (isAuthenticated) {
      loadConfig()
    }
  }, [isAuthenticated])

  if (!isAuthenticated) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen gap-4">
        <p className="text-4xl">Please sign in</p>
        <Button onClick={() => signIn()}>Sign In</Button>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen gap-4">
        <p className="text-xl text-red-600">Configuration Error</p>
        <p className="text-sm text-gray-600">{error}</p>
      </div>
    )
  }

  if (!configLoaded) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-gray-900"></div>
      </div>
    )
  }

  return (
    <GlobalContextProvider>
      <ChatInterface
        title="Clinical Decision Support Agent"
        welcomeMessage="Clinical Decision Support with Epic 3LO"
        description="I can help analyze patient medications, allergies, and lab results from Epic FHIR. On first use, you'll be prompted to authorize access to patient data via Epic login (3-Legged OAuth). Ask me to check drug safety, interactions, or contraindications for specific patients."
      />
    </GlobalContextProvider>
  )
}
