// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
//
// Threat T12 mitigation:
// On every app load, evict any legacy `pa_orders` entries that older app
// versions may have written to localStorage. Order data is now kept in
// memory only (see src/lib/ordersStore.ts).

"use client"

import { useEffect } from "react"

const LEGACY_KEYS = [
  "pa_orders",
  "pa_evidence",
  "pa_decisions",
] as const

export function LegacyStorageEviction() {
  useEffect(() => {
    if (typeof window === "undefined") return
    try {
      for (const k of LEGACY_KEYS) {
        window.localStorage.removeItem(k)
      }
    } catch {
      // best effort — not all browsers permit access in private mode
    }
  }, [])
  return null
}
