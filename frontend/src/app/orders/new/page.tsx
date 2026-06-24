"use client"

import React, { useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { useAuth } from "@/hooks/useAuth"
import { useAuthToken } from "@/lib/useAuthToken"
import { upsertOrder } from "@/lib/ordersStore"
import { GlobalContextProvider } from "@/app/context/GlobalContext"
import { invokeAgentCore, generateSessionId, setAgentConfig } from "@/services/agentCoreService"
import { usePatient } from "@/app/context/PatientContext"
import {
  Shield, ArrowLeft, Loader2, CheckCircle, AlertCircle, ArrowRight,
  User, Stethoscope, Building2, Package, Activity, FileText, Search
} from "lucide-react"
import { useRouter } from "next/navigation"

function NewOrderForm() {
  const { isAuthenticated, signIn } = useAuth()
  const { accessToken, userId, idToken } = useAuthToken()
  const { patient } = usePatient()
  const router = useRouter()
  const [configLoaded, setConfigLoaded] = useState(false)
  const [apiUrl, setApiUrl] = useState<string | null>(null)
  const [sessionId] = useState(() => generateSessionId())
  const [error, setError] = useState<string | null>(null)

  // Form fields
  const [patientId, setPatientId] = useState("")
  const [patientName, setPatientName] = useState("")
  const [orderType, setOrderType] = useState<"procedure" | "medication" | "device">("procedure")
  const [code, setCode] = useState("")
  const [description, setDescription] = useState("")
  const [diagnosisCode, setDiagnosisCode] = useState("")
  const [diagnosisDesc, setDiagnosisDesc] = useState("")
  const [payorName, setPayorName] = useState("")
  const [memberId, setMemberId] = useState("")
  const [urgency, setUrgency] = useState("routine")
  const [clinicalNotes, setClinicalNotes] = useState("")

  // Lookup
  const [lookupLoading, setLookupLoading] = useState(false)
  const [lookupDone, setLookupDone] = useState(false)
  const [patientConditions, setPatientConditions] = useState<string[]>([])

  // Eligibility check
  const [eligChecking, setEligChecking] = useState(false)
  const [eligResult, setEligResult] = useState<{ paRequired: boolean; reason: string } | null>(null)

  // Submission
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    async function loadConfig() {
      try {
        const r = await fetch("/aws-exports.json")
        if (!r.ok) throw new Error("Failed to load config")
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

  // Prefill patient identity from the selected-patient context (if any).
  useEffect(() => {
    if (patient?.id) {
      setPatientId(patient.id)
      if (patient.name) setPatientName(patient.name)
      if (patient.payorName) setPayorName(patient.payorName)
      if (patient.memberId) setMemberId(patient.memberId)
    }
  }, [patient])

  const callAgent = async (prompt: string): Promise<string> => {
    if (!accessToken || !userId) throw new Error("Auth required. Sign in again.")
    let result = ""
    await invokeAgentCore(prompt, sessionId, (s: string) => { result = s }, accessToken, userId, undefined)
    return result
  }

  /* Patient Lookup — deterministic call to the /patients API (fast, reliable).
     Returns demographics + active Coverage (payer/member ID) + conditions, so
     the form auto-populates without depending on slow LLM text parsing. */
  const lookupPatient = async () => {
    const id = patientId.trim()
    if (!id || !apiUrl) return
    setLookupLoading(true); setLookupDone(false); setError(null)
    try {
      const resp = await fetch(`${apiUrl}patients?q=${encodeURIComponent(id)}`, {
        headers: { Authorization: `Bearer ${idToken}` },
      })
      if (!resp.ok) throw new Error(`Patient lookup failed (HTTP ${resp.status})`)
      const data = await resp.json()
      const p = (data.patients || [])[0]
      if (!p) { setError("No patient found for that ID."); return }
      if (p.name) setPatientName(p.name)
      if (p.payorName) setPayorName(p.payorName)
      if (p.memberId) setMemberId(p.memberId)
      if (Array.isArray(p.conditions)) setPatientConditions(p.conditions)
      setLookupDone(true)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Patient lookup failed")
    } finally { setLookupLoading(false) }
  }

  /* Auto-trigger the lookup once a full patient ID has been entered/pasted. */
  useEffect(() => {
    if (!apiUrl || !idToken) return
    const id = patientId.trim()
    if (!/^[0-9a-fA-F-]{16,}$/.test(id)) return
    const t = setTimeout(() => { lookupPatient() }, 600)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [patientId, apiUrl, idToken])

  /* Eligibility Check — runs automatically when order is submitted */
  const checkEligibilityAndSubmit = async () => {
    if (!configLoaded) return
    setEligChecking(true); setError(null); setEligResult(null)
    try {
      const resp = await callAgent(
        `Check if prior authorization is required for the following order:
- Patient: ${patientId} (${patientName})
- Order Type: ${orderType}
- Code: ${code} (${description})
- Diagnosis: ${diagnosisCode} ${diagnosisDesc}
- Payor: ${payorName}, Member ID: ${memberId}
- Urgency: ${urgency}

Use the payor policy tools to check if this ${orderType} requires prior authorization from ${payorName}. 
Return EXACTLY one of these on the first line:
PA_REQUIRED: YES
PA_REQUIRED: NO

Then explain why in 1-2 sentences.`
      )
      console.log("[ELIG] Agent response:", resp.substring(0, 300))

      const paRequired = resp.toUpperCase().includes("PA_REQUIRED: YES") ||
        resp.toLowerCase().includes("prior authorization is required") ||
        resp.toLowerCase().includes("pa is required")

      const reason = resp.split('\n').filter(l => l.trim().length > 10 && !l.includes("PA_REQUIRED"))[0]?.replace(/\*\*/g, '').trim() || ""

      setEligResult({ paRequired, reason })

      // Create the order
      const orderId = crypto.randomUUID().slice(0, 8)
      const now = new Date().toISOString()
      const order = {
        id: orderId,
        patientId,
        patientName,
        orderType,
        code,
        description,
        diagnosisCode,
        diagnosisDesc,
        payorName,
        memberId,
        urgency,
        clinicalNotes,
        paRequired,
        paStatus: paRequired ? "pending" as const : "not_required" as const,
        preAuthRef: null,
        createdAt: now,
        updatedAt: now,
      }
      upsertOrder(order)

      if (paRequired) {
        // Redirect to PA workflow after a brief delay to show the result
        setTimeout(() => {
          router.push(`/orders/prior-auth?id=${orderId}`)
        }, 2000)
      } else {
        setTimeout(() => {
          router.push("/")
        }, 2000)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Eligibility check failed")
    } finally { setEligChecking(false) }
  }

  if (!isAuthenticated) return (
    <div className="flex flex-col items-center justify-center min-h-screen gap-4 bg-gradient-to-br from-blue-50 to-indigo-100">
      <Shield className="h-16 w-16 text-blue-600" />
      <p className="text-3xl font-bold text-gray-800">New Order</p>
      <Button size="lg" onClick={() => signIn()}>Sign In to Continue</Button>
    </div>
  )

  if (!configLoaded && !error) return (
    <div className="flex items-center justify-center min-h-screen bg-gray-50">
      <Loader2 className="h-8 w-8 animate-spin text-blue-600" />
    </div>
  )

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-gradient-to-r from-blue-700 to-indigo-800 text-white">
        <div className="max-w-4xl mx-auto px-4 py-4 flex items-center gap-4">
          <Button variant="ghost" size="sm" onClick={() => router.push("/")} className="text-white hover:bg-white/20">
            <ArrowLeft className="h-4 w-4 mr-1" /> Dashboard
          </Button>
          <Shield className="h-6 w-6" />
          <h1 className="text-xl font-bold">New Order</h1>
        </div>
      </div>

      {error && (
        <div className="max-w-4xl mx-auto px-4 mt-4">
          <div className="bg-red-50 border border-red-200 rounded-lg p-4 flex items-center gap-2">
            <AlertCircle className="h-5 w-5 text-red-500 flex-shrink-0" />
            <p className="text-sm text-red-700">{error}</p>
          </div>
        </div>
      )}

      <div className="max-w-4xl mx-auto px-4 py-8">
        {/* Eligibility Result Overlay */}
        {eligResult && (
          <div className={`mb-6 rounded-xl p-6 border-2 ${
            eligResult.paRequired
              ? "bg-yellow-50 border-yellow-300"
              : "bg-green-50 border-green-300"
          }`}>
            <div className="flex items-center gap-3">
              {eligResult.paRequired ? (
                <AlertCircle className="h-8 w-8 text-yellow-600" />
              ) : (
                <CheckCircle className="h-8 w-8 text-green-600" />
              )}
              <div>
                <h3 className={`text-lg font-bold ${eligResult.paRequired ? "text-yellow-800" : "text-green-800"}`}>
                  {eligResult.paRequired ? "Prior Authorization Required" : "No Prior Authorization Needed"}
                </h3>
                <p className="text-sm text-gray-600 mt-1">{eligResult.reason}</p>
                <p className="text-xs text-gray-400 mt-2">
                  {eligResult.paRequired
                    ? "Redirecting to prior authorization workflow..."
                    : "Order created. Redirecting to dashboard..."}
                </p>
              </div>
            </div>
          </div>
        )}

        <Card className="shadow-lg">
          <CardHeader className="bg-gradient-to-r from-blue-50 to-indigo-50 rounded-t-lg">
            <CardTitle className="flex items-center gap-2">
              <Package className="h-5 w-5 text-blue-600" /> Order Details
            </CardTitle>
            <p className="text-sm text-gray-500 mt-1">
              Submit an order for a procedure, medication, or device. The system will automatically check if prior authorization is required.
            </p>
          </CardHeader>
          <CardContent className="pt-6">
            <form onSubmit={(e) => { e.preventDefault(); checkEligibilityAndSubmit() }} className="space-y-8">
              {/* Patient */}
              <div>
                <h3 className="text-sm font-bold text-blue-700 mb-3 uppercase tracking-wider flex items-center gap-2">
                  <User className="h-4 w-4" /> Patient Information
                </h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium mb-1">Patient ID <span className="text-red-500">*</span></label>
                    <div className="flex gap-2">
                      <Input value={patientId} onChange={e => { setPatientId(e.target.value); setLookupDone(false) }} placeholder="e.g. f438e14c-9993-4813-a95e-..." required />
                      <Button type="button" variant="outline" size="sm" onClick={lookupPatient} disabled={lookupLoading || !patientId.trim()}>
                        {lookupLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <><Search className="h-4 w-4 mr-1" /> Lookup</>}
                      </Button>
                    </div>
                    {lookupDone && <p className="text-xs text-green-600 mt-1 flex items-center gap-1"><CheckCircle className="h-3 w-3" /> Patient found</p>}
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-1">Patient Name</label>
                    <Input value={patientName} onChange={e => setPatientName(e.target.value)} placeholder="Auto-populated from HealthLake" />
                  </div>
                </div>
                {lookupDone && patientConditions.length > 0 && (
                  <div className="mt-3 p-3 bg-blue-50 rounded-lg border border-blue-200">
                    <p className="text-xs font-semibold text-blue-700 mb-1">Active Conditions</p>
                    <div className="flex flex-wrap gap-1">
                      {patientConditions.slice(0, 6).map((c, i) => (
                        <span key={i} className="text-xs bg-white px-2 py-0.5 rounded border text-gray-700">{c}</span>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* Order */}
              <div>
                <h3 className="text-sm font-bold text-purple-700 mb-3 uppercase tracking-wider flex items-center gap-2">
                  <Stethoscope className="h-4 w-4" /> Order Information
                </h3>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div>
                    <label className="block text-sm font-medium mb-1">Order Type <span className="text-red-500">*</span></label>
                    <Select value={orderType} onValueChange={(v: any) => setOrderType(v)}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="procedure">Procedure (CPT)</SelectItem>
                        <SelectItem value="medication">Medication (NDC/RxNorm)</SelectItem>
                        <SelectItem value="device">Medical Device (HCPCS)</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-1">Code <span className="text-red-500">*</span></label>
                    <Input value={code} onChange={e => setCode(e.target.value)} placeholder={orderType === "procedure" ? "e.g. 72148" : orderType === "medication" ? "e.g. 0069-3150-83" : "e.g. E0601"} required />
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-1">Description <span className="text-red-500">*</span></label>
                    <Input value={description} onChange={e => setDescription(e.target.value)} placeholder={orderType === "procedure" ? "e.g. MRI Lumbar Spine" : orderType === "medication" ? "e.g. Humira 40mg" : "e.g. CPAP Machine"} required />
                  </div>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
                  <div>
                    <label className="block text-sm font-medium mb-1">Diagnosis Code (ICD-10)</label>
                    <Input value={diagnosisCode} onChange={e => setDiagnosisCode(e.target.value)} placeholder="e.g. M54.5" />
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-1">Diagnosis Description</label>
                    <Input value={diagnosisDesc} onChange={e => setDiagnosisDesc(e.target.value)} placeholder="e.g. Low back pain" />
                  </div>
                </div>
              </div>

              {/* Insurance */}
              <div>
                <h3 className="text-sm font-bold text-green-700 mb-3 uppercase tracking-wider flex items-center gap-2">
                  <Building2 className="h-4 w-4" /> Insurance Information
                </h3>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div>
                    <label className="block text-sm font-medium mb-1">Payor <span className="text-red-500">*</span></label>
                    <Input value={payorName} onChange={e => setPayorName(e.target.value)} placeholder="e.g. Blue Cross Blue Shield" required />
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-1">Member ID <span className="text-red-500">*</span></label>
                    <Input value={memberId} onChange={e => setMemberId(e.target.value)} placeholder="e.g. MEM-445566" required />
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-1">Urgency</label>
                    <Select value={urgency} onValueChange={setUrgency}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="routine">Routine</SelectItem>
                        <SelectItem value="urgent">Urgent</SelectItem>
                        <SelectItem value="emergency">Emergency</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>
              </div>

              {/* Notes */}
              <div>
                <label className="block text-sm font-medium mb-1">Clinical Notes (optional)</label>
                <Textarea value={clinicalNotes} onChange={e => setClinicalNotes(e.target.value)} placeholder="Additional clinical context for the order..." rows={3} />
              </div>

              {/* Submit */}
              <div className="flex items-center gap-4 pt-2">
                <Button
                  type="submit"
                  size="lg"
                  disabled={!patientId || !code || !description || !payorName || !memberId || eligChecking || !!eligResult}
                  className="px-10 bg-blue-600 hover:bg-blue-700"
                >
                  {eligChecking ? (
                    <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Checking Eligibility...</>
                  ) : (
                    <><ArrowRight className="h-4 w-4 mr-2" /> Submit Order</>
                  )}
                </Button>
                <p className="text-xs text-gray-400">
                  The system will verify if prior authorization is required before processing.
                </p>
              </div>
            </form>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

export default function NewOrderPage() {
  return <GlobalContextProvider><NewOrderForm /></GlobalContextProvider>
}
