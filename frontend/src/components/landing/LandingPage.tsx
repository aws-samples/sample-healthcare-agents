// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

/**
 * Landing Page Component
 *
 * Displays available healthcare agents as cards that users can select.
 */

"use client"

import React from "react"
import { useRouter } from "next/navigation"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Shield } from "lucide-react"

interface AgentCard {
  id: string
  title: string
  description: string
  icon: React.ReactNode
  route: string
  color: string
}

const agents: AgentCard[] = [
  {
    id: "prior-auth",
    title: "Prior Authorization Agent",
    description: "Submit and manage prior authorization requests. Gathers clinical data, assesses medical necessity, checks payor requirements, and assembles authorization requests.",
    icon: <Shield className="w-8 h-8" />,
    route: "/prior-auth",
    color: "text-blue-600"
  },
  {
    id: "eligibility",
    title: "Eligibility Verification Agent",
    description: "Verify patient insurance eligibility and benefits. Checks coverage status, benefit details, cost sharing, and prior authorization requirements.",
    icon: <Shield className="w-8 h-8" />,
    route: "/eligibility",
    color: "text-green-600"
  },
  {
    id: "safety-agent",
    title: "Hospital Safety Agent",
    description: "Report and analyze patient safety incidents including falls, medication errors, and infections",
    icon: <Shield className="w-8 h-8" />,
    route: "/safety-agent",
    color: "text-orange-600"
  },
]

export function LandingPage() {
  const router = useRouter()

  const handleCardClick = (route: string) => {
    router.push(route)
  }

  return (
    <div className="min-h-screen bg-gradient-to-b from-gray-50 to-gray-100">
      {/* Header */}
      <div className="bg-white shadow-sm border-b">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
          <h1 className="text-3xl font-bold text-gray-900">Healthcare Agents</h1>
          <p className="mt-2 text-gray-600">
            AI-powered prior authorization and eligibility verification on Amazon Bedrock AgentCore
          </p>
        </div>
      </div>

      {/* Agent Cards */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {agents.map((agent) => (
            <Card
              key={agent.id}
              className="cursor-pointer hover:shadow-lg transition-all duration-200 hover:-translate-y-1"
              onClick={() => handleCardClick(agent.route)}
            >
              <CardHeader>
                <div className="flex items-center gap-3">
                  <div className={agent.color}>{agent.icon}</div>
                  <CardTitle className="text-xl">{agent.title}</CardTitle>
                </div>
              </CardHeader>
              <CardContent>
                <CardDescription className="text-base">
                  {agent.description}
                </CardDescription>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </div>
  )
}
