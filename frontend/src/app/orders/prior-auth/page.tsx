"use client"

import React, { useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { useAuth } from "@/hooks/useAuth"
import { useAuthToken } from "@/lib/useAuthToken"
import { useOrders, getOrder, updateOrder } from "@/lib/ordersStore"
import { GlobalContextProvider } from "@/app/context/GlobalContext"
import { invokeAgentCore, generateSessionId, setAgentConfig } from "@/services/agentCoreService"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import {
  Shield, ArrowLeft, ArrowRight, CheckCircle, AlertCircle, Loader2,
  User, Stethoscope, Building2, Scale, Activity, Pill, Heart,
  ClipboardList, FileText, Edit, Plus, RefreshCw, X, Save
} from "lucide-react"
import { useRouter, useSearchParams } from "next/navigation"
import DTRQuestionnaireRenderer, { type FHIRQuestionnaireResponse, type AutoFillResult } from "@/components/prior-auth/DTRQuestionnaireRenderer"

const PA_STEPS = [
  { id: 'patient',  label: 'Patient Data',     icon: User },
  { id: 'clinical', label: 'Clinical Evidence', icon: Stethoscope },
  { id: 'policy',   label: 'Policy & DTR',     icon: Building2 },
  { id: 'decision', label: 'Authorization',    icon: Scale },
]

function parseAgentResponse(text: string, section: string): string[] {
  const lines = text.split('\n').map(l => l.trim()).filter(Boolean)
  const items: string[] = []; let inSection = false
  for (const line of lines) {
    if (line.toLowerCase().includes(section.toLowerCase())) { inSection = true; continue }
    if (inSection && (line.startsWith('#') || line.startsWith('**'))) { if (items.length > 0) break }
    if (inSection) {
      const clean = line.replace(/^[-•*]\s*/, '').replace(/^\d+[.)]\s*/, '').replace(/\*\*/g, '').trim()
      if (clean.length > 3) items.push(clean)
    }
  }
  return items.length > 0 ? items : lines.filter(l => !l.startsWith('#')).slice(0, 5).map(l => l.replace(/\*\*/g, '').replace(/^[-•*]\s*/, '').trim())
}

function Stepper({ currentStep, steps }: { currentStep: number; steps: typeof PA_STEPS }) {
  return (
    <div className="w-full bg-white border-b">
      <div className="max-w-5xl mx-auto px-4 py-4">
        <div className="flex items-center justify-between">
          {steps.map((step, idx) => {
            const Icon = step.icon; const isActive = idx === currentStep; const isComplete = idx < currentStep
            return (
              <React.Fragment key={step.id}>
                <div className="flex flex-col items-center gap-1">
                  <div className={`w-10 h-10 rounded-full flex items-center justify-center transition-all ${
                    isComplete ? 'bg-green-500 text-white' : isActive ? 'bg-blue-600 text-white ring-4 ring-blue-100' : 'bg-gray-200 text-gray-400'
                  }`}>{isComplete ? <CheckCircle className="h-5 w-5" /> : <Icon className="h-5 w-5" />}</div>
                  <span className={`text-xs font-medium ${isActive ? 'text-blue-600' : isComplete ? 'text-green-600' : 'text-gray-400'}`}>{step.label}</span>
                </div>
                {idx < steps.length - 1 && <div className={`flex-1 h-0.5 mx-2 ${isComplete ? 'bg-green-500' : 'bg-gray-200'}`} />}
              </React.Fragment>
            )
          })}
        </div>
      </div>
    </div>
  )
}

function DataCard({ icon: Icon, title, items, color = 'blue' }: { icon: any; title: string; items: string[]; color?: string }) {
  const colors: Record<string, string> = { blue: 'border-blue-200 bg-blue-50', green: 'border-green-200 bg-green-50', purple: 'border-purple-200 bg-purple-50', orange: 'border-orange-200 bg-orange-50', red: 'border-red-200 bg-red-50' }
  const iconColors: Record<string, string> = { blue: 'text-blue-600', green: 'text-green-600', purple: 'text-purple-600', orange: 'text-orange-600', red: 'text-red-600' }
  return (
    <div className={`rounded-xl border-2 ${colors[color]} p-4`}>
      <div className="flex items-center gap-2 mb-3">
        <Icon className={`h-5 w-5 ${iconColors[color]}`} />
        <h3 className="font-semibold text-gray-800">{title}</h3>
        <span className="ml-auto text-xs bg-white px-2 py-0.5 rounded-full text-gray-500 border">{items.length}</span>
      </div>
      {items.length > 0 ? (
        <ul className="space-y-1.5">{items.map((item, i) => (
          <li key={i} className="flex items-start gap-2 text-sm text-gray-700">
            <span className="mt-1.5 w-1.5 h-1.5 rounded-full bg-gray-400 flex-shrink-0" /><span>{item}</span>
          </li>
        ))}</ul>
      ) : <p className="text-sm text-gray-500 italic">No data available</p>}
    </div>
  )
}

function LoadingScreen({ message }: { message: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-20 gap-4">
      <div className="relative">
        <div className="w-16 h-16 border-4 border-blue-200 rounded-full animate-spin border-t-blue-600" />
        <Activity className="h-6 w-6 text-blue-600 absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2" />
      </div>
      <p className="text-lg font-medium text-gray-700">{message}</p>
      <p className="text-sm text-gray-500">AI agent is processing...</p>
    </div>
  )
}

function PriorAuthWorkflow() {
  const { isAuthenticated, signIn } = useAuth()
  const { accessToken, userId, idToken } = useAuthToken()
  const router = useRouter()
  const searchParams = useSearchParams()
  const orderId = searchParams.get("id") || ""
  // CDS Hooks deep-link params: when launched from an EHR order-select card,
  // there's no local order — synthesize one from patientId + order context.
  // code is often empty for medications (RxNorm, not CPT), so desc/payor carry
  // the actual order name and payer the agent workflow needs.
  const linkPatientId = searchParams.get("patientId") || ""
  const linkCode = searchParams.get("code") || ""
  const linkDesc = searchParams.get("desc") || ""
  const linkPayor = searchParams.get("payor") || ""

  const [order, setOrder] = useState<any>(null)
  const [configLoaded, setConfigLoaded] = useState(false)
  const [apiUrl, setApiUrl] = useState<string | null>(null)
  const [sessionId] = useState(() => generateSessionId())
  const [currentStep, setCurrentStep] = useState(0)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [autoStarted, setAutoStarted] = useState(false)

  const [patientData, setPatientData] = useState({ demographics: [] as string[], conditions: [] as string[], medications: [] as string[], allergies: [] as string[] })
  const [clinicalEvidence, setClinicalEvidence] = useState({ observations: [] as string[], labResults: [] as string[], clinicalNotes: [] as string[] })
  const [policyCheck, setPolicyCheck] = useState({ requirements: [] as string[], criteriaMet: [] as string[], criteriaNotMet: [] as string[], documentationNeeded: [] as string[] })
  const [decision, setDecision] = useState({ status: 'pending' as string, summary: '', reasoning: [] as string[], nextSteps: [] as string[] })
  const [rawResponses, setRawResponses] = useState<Record<string, string>>({})
  const [dtrQuestionnaireUrl, setDtrQuestionnaireUrl] = useState<string | null>(null)
  const [dtrAutoFillResults] = useState<AutoFillResult[]>([])
  const [questionnaireResponse, setQuestionnaireResponse] = useState<FHIRQuestionnaireResponse | null>(null)
  const [pasBundleJson, setPasBundleJson] = useState<string | null>(null)
  const [claimResponseJson, setClaimResponseJson] = useState<string | null>(null)
  // User-initiated "Save Authorization to HealthLake" state.
  const [savingAuth, setSavingAuth] = useState(false)
  const [savedAuthId, setSavedAuthId] = useState<string | null>(null)
  const [saveAuthError, setSaveAuthError] = useState<string | null>(null)

  // Remediation / compliance fix state
  const [supplementalNotes, setSupplementalNotes] = useState("")
  const [additionalClinicalNotes, setAdditionalClinicalNotes] = useState("")
  const [editingCriteria, setEditingCriteria] = useState(false)
  const [remediationItems, setRemediationItems] = useState<{issue: string; resolution: string; resolved: boolean}[]>([])
  const [reEvaluating, setReEvaluating] = useState(false)

  useEffect(() => {
    if (orderId) {
      const found = getOrder(orderId)
      setOrder(found || null)
    } else if (linkPatientId) {
      // Launched from a CDS Hooks order-select card — build a transient order
      // so the agent-backed workflow can run for this patient + order.
      setOrder({
        id: "",
        patientId: linkPatientId,
        patientName: linkPatientId,
        code: linkCode,
        description: linkDesc || linkCode,
        payorName: linkPayor,
        _fromCdsHooks: true,
      })
    }
  }, [orderId, linkPatientId, linkCode, linkDesc, linkPayor])

  // For CDS-launched orders, resolve the patient's real name + active Coverage
  // (payer/member ID) from HealthLake via the deterministic /patients API, so
  // the header/fields auto-populate instead of showing the raw patient UUID.
  useEffect(() => {
    async function enrich() {
      if (!order?._fromCdsHooks || order._enriched || !apiUrl || !idToken) return
      try {
        const r = await fetch(`${apiUrl}patients?q=${encodeURIComponent(order.patientId)}`, {
          headers: { Authorization: `Bearer ${idToken}` },
        })
        if (!r.ok) return
        const data = await r.json()
        const p = (data.patients || [])[0]
        if (!p) return
        setOrder((o: any) => ({
          ...o,
          patientName: p.name || o.patientName,
          payorName: o.payorName || p.payorName || "",
          memberId: p.memberId || o.memberId,
          _enriched: true,
        }))
      } catch {
        /* non-fatal — the agent steps still gather clinical data */
      }
    }
    enrich()
  }, [order, apiUrl, idToken])

  useEffect(() => {
    async function loadConfig() {
      try {
        const r = await fetch("/aws-exports.json"); if (!r.ok) throw new Error("Config load failed")
        const c = await r.json()
        const arn = c.agents?.["prior-authorization-agent"]?.runtimeArn || c.priorAuthRuntimeArn || c.agentRuntimeArn
        if (!arn) throw new Error("Runtime ARN not found")
        await setAgentConfig(arn, c.awsRegion || "us-east-1", "prior-authorization-agent")
        const base = c.feedbackApiUrl || c.patientApiUrl
        if (base) setApiUrl(base.endsWith("/") ? base : base + "/")
        setConfigLoaded(true)
      } catch (e) { setError(e instanceof Error ? e.message : "Config error") }
    }
    if (isAuthenticated) loadConfig()
  }, [isAuthenticated])

  useEffect(() => {
    if (configLoaded && order && !autoStarted) {
      setAutoStarted(true); runStep0()
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [configLoaded, order, autoStarted])

  const callAgent = async (prompt: string): Promise<string> => {
    if (!accessToken || !userId) throw new Error("Auth required.")
    let result = ""
    await invokeAgentCore(prompt, sessionId, (s: string) => { result = s }, accessToken, userId, undefined)
    return result
  }

  const runStep0 = async () => {
    if (!order) return; setIsLoading(true); setError(null)
    try {
      const resp = await callAgent(`Retrieve patient data for patient ${order.patientId}. Get demographics, active conditions (with ICD-10 codes), current medications, and allergies from HealthLake. Format each category as a bullet list.`)
      setRawResponses(p => ({ ...p, patient: resp }))
      setPatientData({ demographics: parseAgentResponse(resp, 'demographic'), conditions: parseAgentResponse(resp, 'condition'), medications: parseAgentResponse(resp, 'medication'), allergies: parseAgentResponse(resp, 'allerg') })
    } catch (e) { setError(e instanceof Error ? e.message : "Error") }
    finally { setIsLoading(false) }
  }

  const runStep1 = async () => {
    if (!order) return; setIsLoading(true); setError(null); setCurrentStep(1)
    try {
      const resp = await callAgent(`For patient ${order.patientId} who needs ${order.description || order.code}, gather clinical evidence: recent observations, lab results, and relevant clinical notes. Check if conservative treatments have been attempted. Format as bullet lists.`)
      setRawResponses(p => ({ ...p, clinical: resp }))
      setClinicalEvidence({ observations: parseAgentResponse(resp, 'observation'), labResults: parseAgentResponse(resp, 'lab'), clinicalNotes: parseAgentResponse(resp, 'note') })
    } catch (e) { setError(e instanceof Error ? e.message : "Error"); setCurrentStep(0) }
    finally { setIsLoading(false) }
  }

  const runStep2 = async () => {
    if (!order) return; setIsLoading(true); setError(null); setCurrentStep(2)
    try {
      const resp = await callAgent(`Check if there is a DTR questionnaire for payer "${order.payorName}" and procedure "${order.code}". Use get_payer_dtr_config. If found return DTR_URL: <url>. Then check ${order.payorName} policy for ${order.code} (${order.description}). List: 1) Requirements, 2) Criteria met, 3) Criteria NOT met, 4) Documentation needed.`)
      setRawResponses(p => ({ ...p, policy: resp }))
      const dtrMatch = resp.match(/DTR_URL:\s*(https?:\/\/\S+)/); if (dtrMatch) setDtrQuestionnaireUrl(dtrMatch[1])
      setPolicyCheck({ requirements: parseAgentResponse(resp, 'requirement'), criteriaMet: parseAgentResponse(resp, 'met'), criteriaNotMet: parseAgentResponse(resp, 'not met'), documentationNeeded: parseAgentResponse(resp, 'documentation') })
    } catch (e) { setError(e instanceof Error ? e.message : "Error"); setCurrentStep(1) }
    finally { setIsLoading(false) }
  }

  const runStep3 = async () => {
    if (!order) return; setIsLoading(true); setError(null); setCurrentStep(3)
    try {
      // Build supplemental context from remediation
      const resolvedItems = remediationItems.filter(r => r.resolved).map(r => `- ${r.issue} → ${r.resolution}`).join('\n')
      const supplementalContext = [
        resolvedItems ? `\nADDRESSED COMPLIANCE GAPS:\n${resolvedItems}` : '',
        supplementalNotes ? `\nADDITIONAL CLINICAL JUSTIFICATION:\n${supplementalNotes}` : '',
        additionalClinicalNotes ? `\nSUPPLEMENTAL CLINICAL NOTES:\n${additionalClinicalNotes}` : '',
      ].filter(Boolean).join('\n')

      const resp = await callAgent(`Based on all data for patient ${order.patientId}, procedure ${order.code} (${order.description}), payor ${order.payorName}: ${supplementalContext ? `\nThe provider has also supplied the following additional information to support this request:${supplementalContext}\n` : ''}Make a FINAL authorization decision. State exactly one of: "Authorization is recommended", "Authorization is denied", or "Additional documentation required". Generate FHIR PAS Bundle and ClaimResponse as: PAS_BUNDLE_JSON: JSON_OBJECT_HERE CLAIM_RESPONSE_JSON: JSON_OBJECT_HERE. Provide: 1) Summary, 2) Reasoning, 3) Next steps.`)
      setRawResponses(p => ({ ...p, decision: resp }))
      const lower = resp.toLowerCase()
      const status = lower.includes('authorization is recommended') ? 'approved' : lower.includes('authorization is denied') ? 'denied' : 'review'
      const decisionData = {
        status, summary: resp.split('\n').find(l => l.trim().length > 10 && !l.includes('PAS_BUNDLE'))?.replace(/[#*]/g, '').trim() || resp.slice(0, 200),
        reasoning: parseAgentResponse(resp, 'reason'), nextSteps: parseAgentResponse(resp, 'next step'),
      }
      setDecision(decisionData)
      const bundleMatch = resp.match(/PAS_BUNDLE_JSON:\s*(\{[\s\S]*?\})\s*(?:CLAIM_RESPONSE_JSON|$)/)
      if (bundleMatch) { try { setPasBundleJson(JSON.stringify(JSON.parse(bundleMatch[1]), null, 2)) } catch {} }
      const crMatch = resp.match(/CLAIM_RESPONSE_JSON:\s*(\{[\s\S]*?\})\s*$/)
      if (crMatch) { try { setClaimResponseJson(JSON.stringify(JSON.parse(crMatch[1]), null, 2)) } catch {} }
      if (orderId) updateOrder(orderId, { paStatus: status === 'review' ? 'pended' : status, paDecision: decisionData })
    } catch (e) { setError(e instanceof Error ? e.message : "Error"); setCurrentStep(2) }
    finally { setIsLoading(false) }
  }

  /* Re-evaluate after user provides supplemental info to fix compliance gaps */
  const reEvaluateCompliance = async () => {
    if (!order) return
    setReEvaluating(true); setError(null)
    try {
      const resolvedItems = remediationItems.filter(r => r.resolved).map(r => `- Issue: ${r.issue} → Resolution: ${r.resolution}`).join('\n')
      const prompt = `The provider has addressed compliance gaps for patient ${order.patientId}, procedure ${order.code} (${order.description}), payor ${order.payorName}.

${resolvedItems ? `RESOLVED ISSUES:\n${resolvedItems}\n` : ''}
${supplementalNotes ? `ADDITIONAL CLINICAL JUSTIFICATION:\n${supplementalNotes}\n` : ''}
${additionalClinicalNotes ? `SUPPLEMENTAL CLINICAL NOTES:\n${additionalClinicalNotes}\n` : ''}

Re-evaluate the policy compliance with this new information. List: 1) Requirements, 2) Criteria now met, 3) Criteria still NOT met, 4) Any remaining documentation needed. Format as bullet lists.`

      const resp = await callAgent(prompt)
      setRawResponses(p => ({ ...p, policy_reeval: resp }))
      setPolicyCheck({
        requirements: parseAgentResponse(resp, 'requirement'),
        criteriaMet: parseAgentResponse(resp, 'met'),
        criteriaNotMet: parseAgentResponse(resp, 'not met'),
        documentationNeeded: parseAgentResponse(resp, 'documentation'),
      })
      setEditingCriteria(false)
    } catch (e) { setError(e instanceof Error ? e.message : "Re-evaluation failed") }
    finally { setReEvaluating(false) }
  }

  /* User-initiated persistence: writes a ClaimResponse to the record only when
     the user explicitly clicks Save. Uses the agent-generated ClaimResponse if
     it parsed cleanly; otherwise synthesizes a minimal valid one from the
     decision + order so Save always works (LLM JSON output is unreliable). */
  const buildClaimResponse = (): any => {
    if (claimResponseJson) {
      try { return JSON.parse(claimResponseJson) } catch { /* fall through */ }
    }
    const outcome = "complete"
    const dispositionPrefix =
      decision.status === "approved" ? "Authorization recommended"
      : decision.status === "denied" ? "Authorization denied"
      : "Additional documentation required"
    return {
      resourceType: "ClaimResponse",
      status: "active",
      type: { coding: [{ system: "http://terminology.hl7.org/CodeSystem/claim-type", code: "professional" }] },
      use: "preauthorization",
      patient: { reference: `Patient/${order.patientId}` },
      created: new Date().toISOString().slice(0, 10),
      insurer: { display: order.payorName || "Unknown payer" },
      outcome,
      disposition: `${dispositionPrefix}: ${decision.summary || order.description || order.code || ""}`.slice(0, 250),
    }
  }

  const saveAuthorization = async () => {
    if (!apiUrl || !idToken) { setSaveAuthError("Save endpoint not configured."); return }
    setSavingAuth(true); setSaveAuthError(null)
    try {
      const resource = buildClaimResponse()
      const r = await fetch(`${apiUrl}authorizations`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${idToken}` },
        body: JSON.stringify({ resource }),
      })
      const data = await r.json().catch(() => ({}))
      if (!r.ok) throw new Error(data.detail || data.error || `Save failed (HTTP ${r.status})`)
      setSavedAuthId(data.id || "saved")
      if (orderId) updateOrder(orderId, { claimResponseId: data.id })
    } catch (e) {
      setSaveAuthError(e instanceof Error ? e.message : "Save failed")
    } finally { setSavingAuth(false) }
  }

  if (!isAuthenticated) return (
    <div className="flex flex-col items-center justify-center min-h-screen gap-4 bg-gradient-to-br from-blue-50 to-indigo-100">
      <Shield className="h-16 w-16 text-blue-600" /><Button size="lg" onClick={() => signIn()}>Sign In</Button>
    </div>
  )
  if (!order) return (
    <div className="flex flex-col items-center justify-center min-h-screen gap-4">
      <AlertCircle className="h-12 w-12 text-gray-300" /><p className="text-gray-500">Order not found</p>
      <Button variant="outline" onClick={() => router.push("/")}>Dashboard</Button>
    </div>
  )
  if (!configLoaded && !error) return <div className="flex items-center justify-center min-h-screen"><Loader2 className="h-8 w-8 animate-spin text-blue-600" /></div>

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="bg-gradient-to-r from-blue-700 to-indigo-800 text-white">
        <div className="max-w-5xl mx-auto px-4 py-4 flex items-center gap-4">
          <Button variant="ghost" size="sm" onClick={() => router.push(`/orders/detail?id=${orderId}`)} className="text-white hover:bg-white/20">
            <ArrowLeft className="h-4 w-4 mr-1" /> Order
          </Button>
          <Shield className="h-6 w-6" />
          <h1 className="text-xl font-bold">Prior Authorization — {order.description || order.code}</h1>
          <span className="ml-auto text-sm text-blue-200">{order.patientName} · {order.payorName}</span>
        </div>
      </div>
      <Stepper currentStep={currentStep} steps={PA_STEPS} />
      {error && (
        <div className="max-w-5xl mx-auto px-4 mt-4">
          <div className="bg-red-50 border border-red-200 rounded-lg p-4 flex items-center gap-2">
            <AlertCircle className="h-5 w-5 text-red-500 flex-shrink-0" /><p className="text-sm text-red-700">{error}</p>
          </div>
        </div>
      )}
      <div className="max-w-5xl mx-auto px-4 py-8">
        {/* Step 0: Patient Data */}
        {currentStep === 0 && (isLoading ? <LoadingScreen message="Retrieving patient data from HealthLake..." /> : (
          <div className="space-y-6">
            <div className="flex items-center justify-between">
              <h2 className="text-2xl font-bold text-gray-800">Patient Data — {order.patientName}</h2>
              <span className="text-sm text-gray-500 bg-gray-100 px-3 py-1 rounded-full">Source: AWS HealthLake</span>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <DataCard icon={User} title="Demographics" items={patientData.demographics} color="blue" />
              <DataCard icon={Heart} title="Active Conditions" items={patientData.conditions} color="red" />
              <DataCard icon={Pill} title="Current Medications" items={patientData.medications} color="purple" />
              <DataCard icon={AlertCircle} title="Allergies" items={patientData.allergies} color="orange" />
            </div>
            <div className="flex justify-between pt-4">
              <Button variant="outline" onClick={() => router.push(`/orders/detail?id=${orderId}`)}><ArrowLeft className="h-4 w-4 mr-2" /> Back to Order</Button>
              <Button onClick={runStep1} className="bg-blue-600 hover:bg-blue-700">Gather Clinical Evidence <ArrowRight className="h-4 w-4 ml-2" /></Button>
            </div>
          </div>
        ))}
        {/* Step 1: Clinical Evidence */}
        {currentStep === 1 && (isLoading ? <LoadingScreen message="Gathering clinical evidence..." /> : (
          <div className="space-y-6">
            <h2 className="text-2xl font-bold text-gray-800">Clinical Evidence</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <DataCard icon={Activity} title="Observations & Vitals" items={clinicalEvidence.observations} color="blue" />
              <DataCard icon={FileText} title="Lab Results" items={clinicalEvidence.labResults} color="green" />
            </div>
            <DataCard icon={Stethoscope} title="Clinical Notes" items={clinicalEvidence.clinicalNotes} color="purple" />

            {/* Supplemental Clinical Notes */}
            <Card className="border-2 border-dashed border-blue-300 bg-blue-50/30">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm flex items-center gap-2 text-blue-700">
                  <Plus className="h-4 w-4" /> Add Supplemental Clinical Notes
                </CardTitle>
                <p className="text-xs text-gray-500">Add additional clinical context, treatment history, or justification to strengthen the authorization request.</p>
              </CardHeader>
              <CardContent>
                <Textarea
                  value={additionalClinicalNotes}
                  onChange={e => setAdditionalClinicalNotes(e.target.value)}
                  placeholder="e.g., Patient has failed 6 weeks of physical therapy (dates: Jan-Feb 2026). Conservative treatment with NSAIDs was ineffective. Specialist referral from Dr. Smith recommends MRI for further evaluation..."
                  rows={4}
                  className="bg-white"
                />
              </CardContent>
            </Card>

            <div className="flex justify-between pt-4">
              <Button variant="outline" onClick={() => setCurrentStep(0)}><ArrowLeft className="h-4 w-4 mr-2" /> Back</Button>
              <Button onClick={runStep2} className="bg-blue-600 hover:bg-blue-700">Check Payor Policy <ArrowRight className="h-4 w-4 ml-2" /></Button>
            </div>
          </div>
        ))}
        {/* Step 2: Policy & DTR */}
        {currentStep === 2 && (isLoading ? <LoadingScreen message={`Checking ${order.payorName} policy...`} /> : (
          <div className="space-y-6">
            <h2 className="text-2xl font-bold text-gray-800">Payor Policy Check</h2>
            {dtrQuestionnaireUrl && !questionnaireResponse && (
              <DTRQuestionnaireRenderer questionnaireUrl={dtrQuestionnaireUrl} patientId={order.patientId} autoFillResults={dtrAutoFillResults} onSubmit={(resp) => setQuestionnaireResponse(resp)} onCancel={() => setDtrQuestionnaireUrl(null)} />
            )}
            {questionnaireResponse && (
              <Card className="border-green-200 bg-green-50"><CardContent className="py-4"><div className="flex items-center gap-2"><CheckCircle className="h-5 w-5 text-green-600" /><span className="font-medium text-green-800">DTR Questionnaire completed</span></div></CardContent></Card>
            )}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <DataCard icon={ClipboardList} title="Requirements" items={policyCheck.requirements} color="blue" />
              <DataCard icon={CheckCircle} title="Criteria Met ✓" items={policyCheck.criteriaMet} color="green" />
              <DataCard icon={AlertCircle} title="Criteria Not Met ✗" items={policyCheck.criteriaNotMet} color="red" />
              <DataCard icon={FileText} title="Documentation Needed" items={policyCheck.documentationNeeded} color="orange" />
            </div>

            {/* Compliance Remediation Panel — shown when there are gaps */}
            {(policyCheck.criteriaNotMet.length > 0 || policyCheck.documentationNeeded.length > 0) && (
              <Card className="border-2 border-amber-300 bg-amber-50/50">
                <CardHeader className="pb-3">
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-base flex items-center gap-2 text-amber-800">
                      <Edit className="h-5 w-5" /> Compliance Remediation
                    </CardTitle>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => {
                        if (!editingCriteria) {
                          // Initialize remediation items from unmet criteria + missing docs
                          const items = [
                            ...policyCheck.criteriaNotMet.map(c => ({ issue: c, resolution: '', resolved: false })),
                            ...policyCheck.documentationNeeded.map(d => ({ issue: `Missing: ${d}`, resolution: '', resolved: false })),
                          ]
                          setRemediationItems(items)
                        }
                        setEditingCriteria(!editingCriteria)
                      }}
                      className="text-amber-700 border-amber-300 hover:bg-amber-100"
                    >
                      {editingCriteria ? <><X className="h-4 w-4 mr-1" /> Cancel</> : <><Edit className="h-4 w-4 mr-1" /> Fix Issues</>}
                    </Button>
                  </div>
                  <p className="text-sm text-amber-700 mt-1">
                    Address the compliance gaps below to reduce the chance of denial. Provide additional documentation or clinical justification for each unmet criterion.
                  </p>
                </CardHeader>

                {editingCriteria && (
                  <CardContent className="space-y-4">
                    {/* Per-issue remediation */}
                    {remediationItems.map((item, idx) => (
                      <div key={idx} className={`rounded-lg border p-3 ${item.resolved ? 'bg-green-50 border-green-200' : 'bg-white border-gray-200'}`}>
                        <div className="flex items-start gap-3">
                          <button
                            type="button"
                            onClick={() => {
                              const updated = [...remediationItems]
                              updated[idx].resolved = !updated[idx].resolved
                              setRemediationItems(updated)
                            }}
                            className={`mt-0.5 w-5 h-5 rounded border-2 flex items-center justify-center flex-shrink-0 transition-colors ${
                              item.resolved ? 'bg-green-500 border-green-500 text-white' : 'border-gray-300 hover:border-green-400'
                            }`}
                            aria-label={item.resolved ? "Mark as unresolved" : "Mark as resolved"}
                          >
                            {item.resolved && <CheckCircle className="h-3 w-3" />}
                          </button>
                          <div className="flex-1 space-y-2">
                            <p className={`text-sm font-medium ${item.resolved ? 'text-green-700 line-through' : 'text-red-700'}`}>
                              {item.issue}
                            </p>
                            <Textarea
                              value={item.resolution}
                              onChange={e => {
                                const updated = [...remediationItems]
                                updated[idx].resolution = e.target.value
                                setRemediationItems(updated)
                              }}
                              placeholder="Describe how this has been addressed (e.g., 'Patient completed 6 weeks of PT per Dr. Smith's notes dated 2/15/2026')"
                              rows={2}
                              className="text-sm"
                            />
                          </div>
                        </div>
                      </div>
                    ))}

                    {/* Additional justification */}
                    <div>
                      <label className="block text-sm font-medium text-amber-800 mb-1">Additional Clinical Justification</label>
                      <Textarea
                        value={supplementalNotes}
                        onChange={e => setSupplementalNotes(e.target.value)}
                        placeholder="Provide any additional clinical context, peer-to-peer review notes, or medical necessity justification..."
                        rows={3}
                      />
                    </div>

                    {/* Re-evaluate button */}
                    <div className="flex items-center gap-3 pt-2">
                      <Button
                        onClick={reEvaluateCompliance}
                        disabled={reEvaluating || remediationItems.filter(r => r.resolved).length === 0}
                        className="bg-amber-600 hover:bg-amber-700"
                      >
                        {reEvaluating ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Re-evaluating...</> : <><RefreshCw className="h-4 w-4 mr-2" /> Re-evaluate Compliance</>}
                      </Button>
                      <span className="text-xs text-gray-500">
                        {remediationItems.filter(r => r.resolved).length} of {remediationItems.length} issues addressed
                      </span>
                    </div>
                  </CardContent>
                )}
              </Card>
            )}

            {/* All clear banner */}
            {policyCheck.criteriaNotMet.length === 0 && policyCheck.documentationNeeded.length === 0 && policyCheck.criteriaMet.length > 0 && (
              <div className="rounded-lg bg-green-50 border border-green-200 p-4 flex items-center gap-3">
                <CheckCircle className="h-6 w-6 text-green-600 flex-shrink-0" />
                <div>
                  <p className="font-medium text-green-800">All compliance criteria met</p>
                  <p className="text-sm text-green-600">No gaps identified. Ready to proceed to authorization decision.</p>
                </div>
              </div>
            )}

            <div className="flex justify-between pt-4">
              <Button variant="outline" onClick={() => setCurrentStep(1)}><ArrowLeft className="h-4 w-4 mr-2" /> Back</Button>
              <Button onClick={runStep3} className="bg-blue-600 hover:bg-blue-700">Get Decision <ArrowRight className="h-4 w-4 ml-2" /></Button>
            </div>
          </div>
        ))}
        {/* Step 3: Decision */}
        {currentStep === 3 && (isLoading ? <LoadingScreen message="AI agent making authorization decision..." /> : (
          <div className="space-y-6">
            <div className={`rounded-2xl p-8 text-center ${
              decision.status === 'approved' ? 'bg-gradient-to-br from-green-50 to-emerald-100 border-2 border-green-300' :
              decision.status === 'denied' ? 'bg-gradient-to-br from-red-50 to-rose-100 border-2 border-red-300' :
              'bg-gradient-to-br from-yellow-50 to-amber-100 border-2 border-yellow-300'
            }`}>
              <div className={`inline-flex items-center justify-center w-20 h-20 rounded-full mb-4 ${decision.status === 'approved' ? 'bg-green-500' : decision.status === 'denied' ? 'bg-red-500' : 'bg-yellow-500'}`}>
                {decision.status === 'approved' ? <CheckCircle className="h-10 w-10 text-white" /> : decision.status === 'denied' ? <AlertCircle className="h-10 w-10 text-white" /> : <ClipboardList className="h-10 w-10 text-white" />}
              </div>
              <h2 className={`text-3xl font-bold mb-2 ${decision.status === 'approved' ? 'text-green-800' : decision.status === 'denied' ? 'text-red-800' : 'text-yellow-800'}`}>
                {decision.status === 'approved' ? 'AUTHORIZED' : decision.status === 'denied' ? 'DENIED' : 'ADDITIONAL REVIEW REQUIRED'}
              </h2>
              <p className="text-gray-600 max-w-2xl mx-auto">{decision.summary}</p>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <DataCard icon={Scale} title="Reasoning" items={decision.reasoning} color={decision.status === 'approved' ? 'green' : decision.status === 'denied' ? 'red' : 'orange'} />
              <DataCard icon={ArrowRight} title="Next Steps" items={decision.nextSteps} color="blue" />
            </div>
            {(pasBundleJson || claimResponseJson) && (
              <div className="space-y-3">
                <h3 className="text-sm font-bold text-gray-600 uppercase tracking-wider">FHIR Resources (Da Vinci PAS)</h3>
                {pasBundleJson && <details className="bg-gray-50 rounded-lg border"><summary className="px-4 py-2 text-sm font-medium text-gray-500 cursor-pointer">PAS Bundle JSON</summary><pre className="px-4 py-3 border-t text-xs text-gray-600 whitespace-pre-wrap overflow-x-auto max-h-64">{pasBundleJson}</pre></details>}
                {claimResponseJson && <details className="bg-gray-50 rounded-lg border"><summary className="px-4 py-2 text-sm font-medium text-gray-500 cursor-pointer">ClaimResponse JSON</summary><pre className="px-4 py-3 border-t text-xs text-gray-600 whitespace-pre-wrap overflow-x-auto max-h-64">{claimResponseJson}</pre></details>}
              </div>
            )}
            {decision.status && decision.status !== 'pending' && (
              <div className="rounded-xl border-2 border-blue-200 bg-blue-50/40 p-4">
                <div className="flex items-center justify-between gap-3 flex-wrap">
                  <div>
                    <p className="font-semibold text-blue-800">Save Authorization</p>
                    <p className="text-xs text-gray-600">The AI agent only recommends the decision. Click to persist this authorization (ClaimResponse) to the patient's record — this is the only action that writes to the record.</p>
                  </div>
                  {savedAuthId ? (
                    <span className="inline-flex items-center gap-2 text-green-700 text-sm font-medium"><CheckCircle className="h-4 w-4" /> Saved (ID: {savedAuthId})</span>
                  ) : (
                    <Button onClick={saveAuthorization} disabled={savingAuth} className="bg-blue-600 hover:bg-blue-700">
                      {savingAuth ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Saving...</> : <><Save className="h-4 w-4 mr-2" /> Save Authorization</>}
                    </Button>
                  )}
                </div>
                {saveAuthError && <p className="text-sm text-red-600 mt-2">{saveAuthError}</p>}
              </div>
            )}
            <div className="flex flex-wrap gap-3 pt-4">
              <Button variant="outline" onClick={() => router.push(`/orders/detail?id=${orderId}`)}><ArrowLeft className="h-4 w-4 mr-2" /> View Order</Button>
              <Button variant="outline" onClick={() => router.push("/")}>Dashboard</Button>
            </div>
            <details className="bg-gray-50 rounded-lg border"><summary className="px-4 py-2 text-sm font-medium text-gray-500 cursor-pointer">Raw Agent Responses</summary>
              <div className="px-4 py-3 border-t space-y-4 max-h-96 overflow-y-auto">
                {Object.entries(rawResponses).map(([k, v]) => (<div key={k}><h4 className="text-xs font-bold text-gray-500 uppercase mb-1">{k}</h4><pre className="text-xs text-gray-600 whitespace-pre-wrap bg-white p-2 rounded border">{v}</pre></div>))}
              </div>
            </details>
          </div>
        ))}
      </div>
    </div>
  )
}

export default function PriorAuthPage() {
  return <GlobalContextProvider><React.Suspense fallback={<div className="flex items-center justify-center min-h-screen"><Loader2 className="h-8 w-8 animate-spin text-blue-600" /></div>}><PriorAuthWorkflow /></React.Suspense></GlobalContextProvider>
}
