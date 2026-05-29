"use client"

import React, { useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { useAuth } from "@/hooks/useAuth"
import { getOrder } from "@/lib/ordersStore"
import { GlobalContextProvider } from "@/app/context/GlobalContext"
import {
  Shield, ArrowLeft, CheckCircle, AlertCircle, Clock, Loader2,
  User, Stethoscope, Building2, Activity, FileText, ArrowRight
} from "lucide-react"
import { useRouter, useSearchParams } from "next/navigation"

interface Order {
  id: string; patientId: string; patientName: string; orderType: string
  code: string; description: string; diagnosisCode?: string; diagnosisDesc?: string
  payorName: string; memberId: string; urgency: string; clinicalNotes?: string
  paRequired: boolean | null; paStatus: string; preAuthRef: string | null
  paDecision?: any; createdAt: string; updatedAt: string
}

const STATUS_CONFIG: Record<string, { bg: string; text: string; icon: React.ReactNode; label: string }> = {
  approved:     { bg: "bg-green-100",  text: "text-green-800",  icon: <CheckCircle className="h-4 w-4" />, label: "Authorized" },
  denied:       { bg: "bg-red-100",    text: "text-red-800",    icon: <AlertCircle className="h-4 w-4" />, label: "Denied" },
  pended:       { bg: "bg-yellow-100", text: "text-yellow-800", icon: <Clock className="h-4 w-4" />,       label: "Pended" },
  pending:      { bg: "bg-blue-100",   text: "text-blue-800",   icon: <Clock className="h-4 w-4" />,       label: "In Progress" },
  not_required: { bg: "bg-gray-100",   text: "text-gray-600",   icon: <CheckCircle className="h-4 w-4" />, label: "PA Not Required" },
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="py-2">
      <p className="text-xs text-gray-500 uppercase tracking-wider">{label}</p>
      <p className="text-sm font-medium text-gray-800">{value || "—"}</p>
    </div>
  )
}

function OrderDetail() {
  const { isAuthenticated, signIn } = useAuth()
  const router = useRouter()
  const searchParams = useSearchParams()
  const orderId = searchParams.get("id") || ""
  const [order, setOrder] = useState<Order | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (orderId) {
      const found = getOrder(orderId) as Order | undefined
      setOrder(found || null)
    }
    setLoading(false)
  }, [orderId])

  if (!isAuthenticated) return (
    <div className="flex flex-col items-center justify-center min-h-screen gap-4 bg-gradient-to-br from-blue-50 to-indigo-100">
      <Shield className="h-16 w-16 text-blue-600" />
      <Button size="lg" onClick={() => signIn()}>Sign In</Button>
    </div>
  )

  if (loading) return <div className="flex items-center justify-center min-h-screen"><Loader2 className="h-8 w-8 animate-spin text-blue-600" /></div>

  if (!order) return (
    <div className="flex flex-col items-center justify-center min-h-screen gap-4">
      <AlertCircle className="h-12 w-12 text-gray-300" />
      <p className="text-gray-500">Order not found</p>
      <Button variant="outline" onClick={() => router.push("/")}>Back to Dashboard</Button>
    </div>
  )

  const sc = STATUS_CONFIG[order.paStatus] || STATUS_CONFIG.pending

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="bg-gradient-to-r from-blue-700 to-indigo-800 text-white">
        <div className="max-w-5xl mx-auto px-4 py-4 flex items-center gap-4">
          <Button variant="ghost" size="sm" onClick={() => router.push("/")} className="text-white hover:bg-white/20">
            <ArrowLeft className="h-4 w-4 mr-1" /> Dashboard
          </Button>
          <Shield className="h-6 w-6" />
          <h1 className="text-xl font-bold">Order {order.id.slice(0, 8)}</h1>
          <span className={`ml-auto inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-sm font-medium ${sc.bg} ${sc.text}`}>
            {sc.icon} {sc.label}
          </span>
        </div>
      </div>

      <div className="max-w-5xl mx-auto px-4 py-6 space-y-6">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <Card>
            <CardHeader className="pb-2"><CardTitle className="text-sm flex items-center gap-2 text-gray-600"><User className="h-4 w-4" /> Patient</CardTitle></CardHeader>
            <CardContent className="space-y-1">
              <InfoRow label="Name" value={order.patientName} />
              <InfoRow label="Patient ID" value={order.patientId.slice(0, 20) + "..."} />
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2"><CardTitle className="text-sm flex items-center gap-2 text-gray-600"><Stethoscope className="h-4 w-4" /> Order</CardTitle></CardHeader>
            <CardContent className="space-y-1">
              <InfoRow label="Type" value={order.orderType} />
              <InfoRow label="Code" value={`${order.code} — ${order.description}`} />
              {order.diagnosisCode && <InfoRow label="Diagnosis" value={`${order.diagnosisCode} ${order.diagnosisDesc || ""}`} />}
              <InfoRow label="Urgency" value={order.urgency} />
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2"><CardTitle className="text-sm flex items-center gap-2 text-gray-600"><Building2 className="h-4 w-4" /> Insurance</CardTitle></CardHeader>
            <CardContent className="space-y-1">
              <InfoRow label="Payor" value={order.payorName} />
              <InfoRow label="Member ID" value={order.memberId} />
              <InfoRow label="PA Required" value={order.paRequired === null ? "Unknown" : order.paRequired ? "Yes" : "No"} />
              {order.preAuthRef && <InfoRow label="Auth Reference" value={order.preAuthRef} />}
            </CardContent>
          </Card>
        </div>

        {/* PA Decision */}
        {order.paDecision && (
          <div className={`rounded-2xl p-6 border-2 ${
            order.paStatus === "approved" ? "bg-green-50 border-green-300" :
            order.paStatus === "denied" ? "bg-red-50 border-red-300" :
            "bg-yellow-50 border-yellow-300"
          }`}>
            <div className="flex items-center gap-3 mb-3">
              {order.paStatus === "approved" ? <CheckCircle className="h-8 w-8 text-green-600" /> :
               order.paStatus === "denied" ? <AlertCircle className="h-8 w-8 text-red-600" /> :
               <Clock className="h-8 w-8 text-yellow-600" />}
              <h2 className="text-xl font-bold">
                {order.paStatus === "approved" ? "AUTHORIZED" : order.paStatus === "denied" ? "DENIED" : "ADDITIONAL REVIEW REQUIRED"}
              </h2>
            </div>
            {order.paDecision.summary && <p className="text-gray-600 mb-3">{order.paDecision.summary}</p>}
            {order.paDecision.reasoning?.length > 0 && (
              <ul className="space-y-1">
                {order.paDecision.reasoning.map((r: string, i: number) => (
                  <li key={i} className="text-sm text-gray-600 flex items-start gap-2">
                    <span className="mt-1.5 w-1.5 h-1.5 rounded-full bg-gray-400 flex-shrink-0" />{r}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {/* Actions */}
        <div className="flex flex-wrap gap-3">
          {order.paRequired && order.paStatus === "pending" && (
            <Button onClick={() => router.push(`/orders/prior-auth?id=${order.id}`)} className="bg-blue-600 hover:bg-blue-700">
              <ArrowRight className="h-4 w-4 mr-2" /> Continue Prior Authorization
            </Button>
          )}
          {order.paRequired && ["approved", "denied", "pended"].includes(order.paStatus) && (
            <Button variant="outline" onClick={() => router.push(`/orders/prior-auth?id=${order.id}`)}>
              <FileText className="h-4 w-4 mr-2" /> View PA Details
            </Button>
          )}
        </div>

        {/* Timeline */}
        <Card>
          <CardHeader><CardTitle className="text-sm text-gray-600 flex items-center gap-2"><Activity className="h-4 w-4" /> Timeline</CardTitle></CardHeader>
          <CardContent>
            <div className="space-y-3">
              <div className="flex items-center gap-3 text-sm">
                <div className="w-2 h-2 rounded-full bg-blue-500" />
                <span className="text-gray-500 w-36">{new Date(order.createdAt).toLocaleString()}</span>
                <span>Order created</span>
              </div>
              {order.paRequired !== null && (
                <div className="flex items-center gap-3 text-sm">
                  <div className={`w-2 h-2 rounded-full ${order.paRequired ? "bg-yellow-500" : "bg-green-500"}`} />
                  <span className="text-gray-500 w-36">{new Date(order.createdAt).toLocaleString()}</span>
                  <span>{order.paRequired ? "Prior authorization required" : "No prior authorization needed"}</span>
                </div>
              )}
              {["approved", "denied"].includes(order.paStatus) && (
                <div className="flex items-center gap-3 text-sm">
                  <div className={`w-2 h-2 rounded-full ${order.paStatus === "approved" ? "bg-green-500" : "bg-red-500"}`} />
                  <span className="text-gray-500 w-36">{new Date(order.updatedAt).toLocaleString()}</span>
                  <span>PA decision: {order.paStatus === "approved" ? "Authorized" : "Denied"}</span>
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

export default function OrderDetailPage() {
  return <GlobalContextProvider><React.Suspense fallback={<div className="flex items-center justify-center min-h-screen"><Loader2 className="h-8 w-8 animate-spin text-blue-600" /></div>}><OrderDetail /></React.Suspense></GlobalContextProvider>
}
