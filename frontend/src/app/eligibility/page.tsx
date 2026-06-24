// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

"use client"

import React, { useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { useAuth } from "@/hooks/useAuth"
import { useAuthToken } from "@/lib/useAuthToken"
import { GlobalContextProvider } from "@/app/context/GlobalContext"
import { usePatient } from "@/app/context/PatientContext"
import { invokeAgentCore, generateSessionId, setAgentConfig } from "@/services/agentCoreService"
import { Shield, Search, CheckCircle, AlertCircle, Loader2, ArrowLeft } from "lucide-react"
import { useRouter } from "next/navigation"

interface WorkflowStep {
  id: string; label: string; status: 'pending' | 'active' | 'complete' | 'error'; detail?: string
}

const INITIAL_STEPS: WorkflowStep[] = [
  { id: 'lookup', label: 'Looking Up Patient', status: 'pending' },
  { id: 'coverage', label: 'Verifying Coverage', status: 'pending' },
  { id: 'benefits', label: 'Checking Benefits', status: 'pending' },
  { id: 'result', label: 'Eligibility Result', status: 'pending' },
]

function EligibilityWorkflow() {
  const { isAuthenticated, signIn } = useAuth()
  const { accessToken, userId } = useAuthToken()
  const { patient } = usePatient()
  const router = useRouter()
  const [configLoaded, setConfigLoaded] = useState(false)
  const [sessionId] = useState(() => generateSessionId())

  const [patientId, setPatientId] = useState("")
  const [patientName, setPatientName] = useState("")
  const [procedureCode, setProcedureCode] = useState("")
  const [procedureDesc, setProcedureDesc] = useState("")
  const [payorName, setPayorName] = useState("")
  const [memberId, setMemberId] = useState("")

  const [isProcessing, setIsProcessing] = useState(false)
  const [steps, setSteps] = useState<WorkflowStep[]>(INITIAL_STEPS)
  const [agentResponse, setAgentResponse] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [showResults, setShowResults] = useState(false)

  useEffect(() => {
    async function loadConfig() {
      try {
        const response = await fetch("/aws-exports.json")
        if (!response.ok) throw new Error("Failed to load configuration")
        const config = await response.json()
        const runtimeArn = config.agents?.["eligibility-verification-agent"]?.runtimeArn || config.eligibilityRuntimeArn || config.agentRuntimeArn
        if (!runtimeArn) throw new Error("Agent Runtime ARN not found")
        await setAgentConfig(runtimeArn, config.awsRegion || "us-east-1", "eligibility-verification-agent")
        setConfigLoaded(true)
      } catch (err) {
        setError(err instanceof Error ? err.message : "Configuration error")
      }
    }
    if (isAuthenticated) loadConfig()
  }, [isAuthenticated])

  // Prefill from selected-patient context.
  useEffect(() => {
    if (patient?.id) {
      setPatientId(patient.id)
      if (patient.name) setPatientName(patient.name)
      if (patient.payorName) setPayorName(patient.payorName)
      if (patient.memberId) setMemberId(patient.memberId)
    }
  }, [patient])

  const updateStep = (stepId: string, status: WorkflowStep['status'], detail?: string) => {
    setSteps(prev => prev.map(s => s.id === stepId ? { ...s, status, detail } : s))
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setAgentResponse("")
    setShowResults(false)
    setSteps(INITIAL_STEPS)
    setIsProcessing(true)

    if (!accessToken || !userId) {
      setError("Authentication required. Please sign out and sign in again.")
      setIsProcessing(false)
      return
    }

    const prompt = `Verify insurance eligibility for the following:

Patient ID: ${patientId}
Patient Name: ${patientName || 'Not provided'}
Procedure Code (CPT): ${procedureCode || 'General eligibility check'}
Procedure Description: ${procedureDesc || 'Not provided'}
Insurance Payor: ${payorName || 'Not provided'}
Member ID: ${memberId || 'Not provided'}

Please check:
1. Patient demographics and identity verification
2. Active insurance coverage status and effective dates
3. Benefits for the requested service including copay, coinsurance, deductible
4. Whether prior authorization is required for this service
5. Provide a complete eligibility summary with next steps`

    updateStep('lookup', 'active')
    setTimeout(() => { updateStep('lookup', 'complete'); updateStep('coverage', 'active') }, 1000)

    try {
      await invokeAgentCore(
        prompt, sessionId,
        (streamedContent: string) => {
          setAgentResponse(streamedContent)
          const lower = streamedContent.toLowerCase()
          if (lower.includes('coverage') || lower.includes('active')) {
            updateStep('coverage', 'complete', 'Coverage verified')
            updateStep('benefits', 'active')
          }
          if (lower.includes('copay') || lower.includes('deductible') || lower.includes('benefit')) {
            updateStep('benefits', 'complete', 'Benefits checked')
            updateStep('result', 'active')
          }
          if (lower.includes('summary') || lower.includes('eligible') || lower.includes('recommend')) {
            updateStep('result', 'complete', 'Verification complete')
          }
        },
        accessToken, userId, undefined
      )
      setSteps(prev => prev.map(s => ({ ...s, status: s.status === 'pending' || s.status === 'active' ? 'complete' : s.status })))
      setShowResults(true)
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Unknown error"
      setError(`Failed: ${msg}`)
      setSteps(prev => prev.map(s => s.status === 'active' ? { ...s, status: 'error', detail: msg } : s))
    } finally {
      setIsProcessing(false)
    }
  }

  if (!isAuthenticated) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen gap-4">
        <p className="text-4xl">Please sign in</p>
        <Button onClick={() => signIn()}>Sign In</Button>
      </div>
    )
  }

  if (!configLoaded && !error) {
    return <div className="flex items-center justify-center min-h-screen"><Loader2 className="h-8 w-8 animate-spin text-green-600" /></div>
  }

  return (
    <div className="min-h-screen bg-gradient-to-b from-gray-50 to-gray-100">
      <div className="bg-white shadow-sm border-b">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-4 flex items-center gap-4">
          <Button variant="outline" size="sm" onClick={() => router.push("/")}><ArrowLeft className="h-4 w-4 mr-1" /> Back</Button>
          <div className="flex items-center gap-2">
            <Shield className="h-6 w-6 text-green-600" />
            <h1 className="text-2xl font-bold text-gray-900">Eligibility Verification</h1>
          </div>
        </div>
      </div>

      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {error && (
          <div className="mb-6 bg-red-50 border-l-4 border-red-500 p-4 rounded">
            <div className="flex items-center gap-2"><AlertCircle className="h-5 w-5 text-red-500" /><p className="text-sm text-red-700">{error}</p></div>
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          <div className="lg:col-span-2">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2"><Search className="h-5 w-5" /> Eligibility Check</CardTitle>
                <CardDescription>Enter patient and insurance details to verify eligibility</CardDescription>
              </CardHeader>
              <CardContent>
                <form onSubmit={handleSubmit} className="space-y-6">
                  <div>
                    <h3 className="text-sm font-semibold text-gray-700 mb-3 uppercase tracking-wide">Patient</h3>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div><label className="block text-sm font-medium mb-1">Patient ID *</label><Input value={patientId} onChange={e => setPatientId(e.target.value)} placeholder="e.g. P001" required disabled={isProcessing} /></div>
                      <div><label className="block text-sm font-medium mb-1">Patient Name</label><Input value={patientName} onChange={e => setPatientName(e.target.value)} placeholder="e.g. Jane Smith" disabled={isProcessing} /></div>
                    </div>
                  </div>
                  <div>
                    <h3 className="text-sm font-semibold text-gray-700 mb-3 uppercase tracking-wide">Service (Optional)</h3>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div><label className="block text-sm font-medium mb-1">CPT Code</label><Input value={procedureCode} onChange={e => setProcedureCode(e.target.value)} placeholder="e.g. 72148" disabled={isProcessing} /></div>
                      <div><label className="block text-sm font-medium mb-1">Description</label><Input value={procedureDesc} onChange={e => setProcedureDesc(e.target.value)} placeholder="e.g. MRI Lumbar Spine" disabled={isProcessing} /></div>
                    </div>
                  </div>
                  <div>
                    <h3 className="text-sm font-semibold text-gray-700 mb-3 uppercase tracking-wide">Insurance</h3>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div><label className="block text-sm font-medium mb-1">Payor</label><Input value={payorName} onChange={e => setPayorName(e.target.value)} placeholder="e.g. UnitedHealthcare" disabled={isProcessing} /></div>
                      <div><label className="block text-sm font-medium mb-1">Member ID</label><Input value={memberId} onChange={e => setMemberId(e.target.value)} placeholder="e.g. UHC-998877" disabled={isProcessing} /></div>
                    </div>
                  </div>
                  <div className="flex gap-3">
                    <Button type="submit" disabled={isProcessing || !patientId} className="px-8">
                      {isProcessing ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Verifying...</> : <><Search className="h-4 w-4 mr-2" /> Verify Eligibility</>}
                    </Button>
                    {showResults && <Button type="button" variant="outline" onClick={() => { setShowResults(false); setAgentResponse(""); setSteps(INITIAL_STEPS) }}>New Check</Button>}
                  </div>
                </form>
              </CardContent>
            </Card>

            {agentResponse && (
              <Card className="mt-6">
                <CardHeader><CardTitle>Eligibility Result</CardTitle></CardHeader>
                <CardContent>
                  <div className="prose prose-sm max-w-none whitespace-pre-wrap text-gray-800 bg-gray-50 p-4 rounded-lg border">{agentResponse}</div>
                </CardContent>
              </Card>
            )}
          </div>

          <div>
            <Card className="sticky top-8">
              <CardHeader><CardTitle className="text-lg">Verification Progress</CardTitle></CardHeader>
              <CardContent>
                <div className="space-y-4">
                  {steps.map((step, idx) => (
                    <div key={step.id} className="flex items-start gap-3">
                      <div className="flex-shrink-0 mt-0.5">
                        {step.status === 'complete' && <CheckCircle className="h-5 w-5 text-green-500" />}
                        {step.status === 'active' && <Loader2 className="h-5 w-5 text-green-500 animate-spin" />}
                        {step.status === 'error' && <AlertCircle className="h-5 w-5 text-red-500" />}
                        {step.status === 'pending' && <div className="h-5 w-5 rounded-full border-2 border-gray-300 flex items-center justify-center"><span className="text-xs text-gray-400">{idx + 1}</span></div>}
                      </div>
                      <div>
                        <p className={`text-sm font-medium ${step.status === 'complete' ? 'text-green-700' : step.status === 'active' ? 'text-green-700' : step.status === 'error' ? 'text-red-700' : 'text-gray-400'}`}>{step.label}</p>
                        {step.detail && <p className="text-xs text-gray-500 mt-0.5">{step.detail}</p>}
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </div>
  )
}

export default function EligibilityPage() {
  return <GlobalContextProvider><EligibilityWorkflow /></GlobalContextProvider>
}
