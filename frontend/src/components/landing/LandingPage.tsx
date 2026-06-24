// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

/**
 * Landing Page Component
 *
 * Patient-first workflow: the user selects a patient, then chooses an action
 * (Prior Authorization or Eligibility Verification) for that patient.
 */

"use client"

import React from "react"
import { useRouter } from "next/navigation"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Shield, Search, User, X, FileCheck, ArrowRight } from "lucide-react"
import { usePatient } from "@/app/context/PatientContext"

interface ActionCard {
  id: string
  title: string
  description: string
  icon: React.ReactNode
  route: string
  color: string
}

const actions: ActionCard[] = [
  {
    id: "prior-auth",
    title: "Prior Authorization",
    description:
      "Gather clinical data, assess medical necessity, check payor requirements, and assemble an authorization request for a procedure, drug, or device.",
    icon: <Shield className="w-7 h-7" />,
    route: "/orders/new",
    color: "text-blue-600",
  },
  {
    id: "eligibility",
    title: "Eligibility Verification",
    description:
      "Verify insurance eligibility and benefits — coverage status, cost sharing, and whether prior authorization is required.",
    icon: <FileCheck className="w-7 h-7" />,
    route: "/eligibility",
    color: "text-green-600",
  },
]

export function LandingPage() {
  const router = useRouter()
  const { patient, clearPatient } = usePatient()

  return (
    <div className="min-h-screen bg-gradient-to-b from-gray-50 to-gray-100">
      {/* Header */}
      <div className="bg-white shadow-sm border-b">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
          <h1 className="text-3xl font-bold text-gray-900">Healthcare Agents</h1>
          <p className="mt-2 text-gray-600">
            AI-powered prior authorization and eligibility verification on Amazon Bedrock AgentCore
          </p>
        </div>
      </div>

      <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
        {!patient ? (
          /* No patient selected: prompt to find one */
          <Card className="text-center">
            <CardHeader>
              <div className="mx-auto text-blue-600">
                <Search className="w-10 h-10" />
              </div>
              <CardTitle className="text-2xl mt-2">Start by selecting a patient</CardTitle>
              <CardDescription className="text-base">
                Search your HealthLake datastore by name or patient ID. Patient demographics will be
                pre-filled into the prior authorization and eligibility workflows.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Button size="lg" onClick={() => router.push("/patients")}>
                <Search className="h-5 w-5 mr-2" /> Find a patient
              </Button>
            </CardContent>
          </Card>
        ) : (
          <>
            {/* Selected patient banner */}
            <div className="flex items-center justify-between bg-blue-50 border border-blue-200 rounded-lg px-5 py-4 mb-8">
              <div className="flex items-center gap-3">
                <User className="h-6 w-6 text-blue-600" />
                <div>
                  <div className="font-semibold text-gray-900 text-lg">
                    {patient.name || "(name unavailable)"}
                  </div>
                  <div className="text-xs text-gray-600">
                    ID: {patient.id} · {patient.gender || "—"} · DOB {patient.birthDate || "—"}
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Button variant="outline" size="sm" onClick={() => router.push("/patients")}>
                  <Search className="h-4 w-4 mr-1" /> Change patient
                </Button>
                <Button variant="ghost" size="sm" onClick={() => clearPatient()} title="Clear patient">
                  <X className="h-4 w-4" />
                </Button>
              </div>
            </div>

            {/* Actions for the selected patient */}
            <h2 className="text-lg font-semibold text-gray-800 mb-4">Choose an action for this patient</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {actions.map((a) => (
                <Card
                  key={a.id}
                  className="cursor-pointer hover:shadow-lg transition-all duration-200 hover:-translate-y-1"
                  onClick={() => router.push(a.route)}
                >
                  <CardHeader>
                    <div className="flex items-center gap-3">
                      <div className={a.color}>{a.icon}</div>
                      <CardTitle className="text-xl">{a.title}</CardTitle>
                      <ArrowRight className="h-5 w-5 ml-auto text-gray-400" />
                    </div>
                  </CardHeader>
                  <CardContent>
                    <CardDescription className="text-base">{a.description}</CardDescription>
                  </CardContent>
                </Card>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  )
}
