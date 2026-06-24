// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

"use client"

import React, { useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { useAuth } from "@/hooks/useAuth"
import { useAuthToken } from "@/lib/useAuthToken"
import { usePatient } from "@/app/context/PatientContext"
import { Search, Loader2, User, ArrowRight, AlertCircle, ArrowLeft } from "lucide-react"
import { useRouter } from "next/navigation"

interface PatientResult {
  id: string
  name?: string
  birthDate?: string
  gender?: string
}

export default function PatientSearchPage() {
  const { isAuthenticated, signIn } = useAuth()
  const { idToken } = useAuthToken()
  const { setPatient } = usePatient()
  const router = useRouter()

  const [apiUrl, setApiUrl] = useState<string | null>(null)
  const [query, setQuery] = useState("")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [results, setResults] = useState<PatientResult[]>([])

  useEffect(() => {
    async function loadConfig() {
      try {
        const r = await fetch("/aws-exports.json")
        if (!r.ok) throw new Error("Failed to load configuration")
        const c = await r.json()
        const base = c.feedbackApiUrl || c.patientApiUrl
        if (!base) throw new Error("Patient search API not found in configuration")
        setApiUrl(base.endsWith("/") ? base : base + "/")
      } catch (e) {
        setError(e instanceof Error ? e.message : "Configuration error")
      }
    }
    if (isAuthenticated) loadConfig()
  }, [isAuthenticated])

  async function runSearch(e?: React.FormEvent) {
    e?.preventDefault()
    if (!query.trim() || !apiUrl) return
    setLoading(true)
    setError(null)
    setResults([])

    try {
      const resp = await fetch(`${apiUrl}patients?q=${encodeURIComponent(query.trim())}`, {
        headers: { Authorization: `Bearer ${idToken}` },
      })
      if (!resp.ok) throw new Error(`Search failed (HTTP ${resp.status})`)
      const data = await resp.json()
      const parsed: PatientResult[] = (data.patients || []).filter((p: PatientResult) => p && p.id)
      setResults(parsed)
      if (parsed.length === 0) setError("No patients found. Try a different name or a patient ID.")
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed")
    } finally {
      setLoading(false)
    }
  }

  function selectPatient(p: PatientResult) {
    setPatient({ id: p.id, name: p.name, birthDate: p.birthDate, gender: p.gender })
    router.push("/")
  }

  const configLoaded = !!apiUrl

  if (!isAuthenticated) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen gap-4">
        <p className="text-2xl">Please sign in</p>
        <Button onClick={() => signIn()}>Sign In</Button>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gradient-to-b from-gray-50 to-gray-100">
      <div className="bg-white shadow-sm border-b">
        <div className="max-w-4xl mx-auto px-4 py-6 flex items-center gap-3">
          <Button variant="ghost" size="sm" onClick={() => router.push("/")}>
            <ArrowLeft className="h-4 w-4 mr-1" /> Home
          </Button>
          <h1 className="text-2xl font-bold text-gray-900">Find a Patient</h1>
        </div>
      </div>

      <div className="max-w-4xl mx-auto px-4 py-8">
        <form onSubmit={runSearch} className="flex gap-2 mb-6">
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search by patient name or paste a patient ID"
            disabled={!configLoaded || loading}
          />
          <Button type="submit" disabled={!configLoaded || loading || !query.trim()}>
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
            <span className="ml-2">Search</span>
          </Button>
        </form>

        {!configLoaded && !error && (
          <p className="text-sm text-gray-500">Loading configuration…</p>
        )}

        {error && (
          <div className="flex items-center gap-2 text-amber-700 bg-amber-50 border border-amber-200 rounded-md p-3 mb-4">
            <AlertCircle className="h-4 w-4" /> <span className="text-sm">{error}</span>
          </div>
        )}

        <div className="space-y-3">
          {results.map((p) => (
            <Card key={p.id} className="cursor-pointer hover:shadow-md transition" onClick={() => selectPatient(p)}>
              <CardHeader className="pb-2">
                <CardTitle className="text-lg flex items-center gap-2">
                  <User className="h-5 w-5 text-blue-600" />
                  {p.name || "(name unavailable)"}
                  <ArrowRight className="h-4 w-4 ml-auto text-gray-400" />
                </CardTitle>
              </CardHeader>
              <CardContent className="text-sm text-gray-600">
                <div>ID: {p.id}</div>
                <div>
                  {p.gender || "—"} · DOB {p.birthDate || "—"}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </div>
  )
}
