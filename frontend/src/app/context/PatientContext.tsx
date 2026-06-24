// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
//
// PHI handling (aligns with the Threat T3 mitigation in src/lib/useAuthToken.ts):
// The selected patient's demographics (name, birthDate, gender, member ID) are
// PHI and are kept in memory only. They are NEVER written to web storage.
//
// To survive a full page reload we persist ONLY the opaque FHIR patient id to
// sessionStorage, then re-fetch the demographics from the authenticated
// /patients API on hydration. Plain client-side navigation keeps this provider
// mounted, so the in-memory record already survives it.

"use client"

import { createContext, PropsWithChildren, useContext, useEffect, useState } from "react"
import { useAuthToken } from "@/lib/useAuthToken"

export interface SelectedPatient {
  id: string
  name?: string
  birthDate?: string
  gender?: string
  payorName?: string
  memberId?: string
  providerName?: string
  providerNpi?: string
}

interface PatientContextType {
  patient: SelectedPatient | null
  setPatient: (p: SelectedPatient | null) => void
  clearPatient: () => void
}

// Stores only the opaque patient id (not PHI). Renamed from the previous
// "selectedPatient" key so any legacy full-record values are ignored/dropped.
const STORAGE_KEY = "selectedPatientId"

const PatientContext = createContext<PatientContextType | undefined>(undefined)

export function PatientContextProvider({ children }: PropsWithChildren) {
  const [patient, setPatientState] = useState<SelectedPatient | null>(null)
  const { idToken, isAuthenticated } = useAuthToken()

  // Hydrate from sessionStorage on mount: restore only the id, so the UI knows
  // a patient is selected. Demographics are re-fetched below (never stored).
  useEffect(() => {
    if (typeof window === "undefined") return
    try {
      // Drop any legacy full-record value from the old "selectedPatient" key.
      window.sessionStorage.removeItem("selectedPatient")
      const id = window.sessionStorage.getItem(STORAGE_KEY)
      if (id) setPatientState((prev) => prev ?? { id })
    } catch {
      /* ignore */
    }
  }, [])

  // Re-fetch PHI for the restored id once authenticated. Keeps demographics in
  // memory only; nothing sensitive is persisted.
  useEffect(() => {
    async function enrich() {
      if (!isAuthenticated || !idToken || !patient?.id || patient.name) return
      try {
        const cfgResp = await fetch("/aws-exports.json")
        if (!cfgResp.ok) return
        const cfg = await cfgResp.json()
        const base = cfg.feedbackApiUrl || cfg.patientApiUrl
        if (!base) return
        const apiUrl = base.endsWith("/") ? base : base + "/"
        const r = await fetch(`${apiUrl}patients?q=${encodeURIComponent(patient.id)}`, {
          headers: { Authorization: `Bearer ${idToken}` },
        })
        if (!r.ok) return
        const data = await r.json()
        const p = (data.patients || [])[0]
        if (!p) return
        setPatientState((prev) =>
          prev && prev.id === patient.id
            ? {
                ...prev,
                name: p.name ?? prev.name,
                birthDate: p.birthDate ?? prev.birthDate,
                gender: p.gender ?? prev.gender,
                payorName: p.payorName ?? prev.payorName,
                memberId: p.memberId ?? prev.memberId,
              }
            : prev,
        )
      } catch {
        /* non-fatal — pages can re-fetch on demand */
      }
    }
    enrich()
  }, [isAuthenticated, idToken, patient?.id, patient?.name])

  const setPatient = (p: SelectedPatient | null) => {
    setPatientState(p)
    try {
      if (typeof window !== "undefined") {
        // Persist only the opaque id — never PHI.
        if (p?.id) window.sessionStorage.setItem(STORAGE_KEY, p.id)
        else window.sessionStorage.removeItem(STORAGE_KEY)
      }
    } catch {
      /* ignore */
    }
  }

  const clearPatient = () => setPatient(null)

  return (
    <PatientContext.Provider value={{ patient, setPatient, clearPatient }}>
      {children}
    </PatientContext.Provider>
  )
}

export function usePatient() {
  const ctx = useContext(PatientContext)
  if (ctx === undefined) {
    throw new Error("usePatient must be used within a PatientContextProvider")
  }
  return ctx
}
