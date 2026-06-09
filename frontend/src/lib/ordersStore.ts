// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
//
// Threat T12 mitigation:
// Order metadata (patientId, procedure, decision) MUST NOT live in
// `localStorage`. localStorage persists across browser sessions and shared
// devices, leaking PHI. This module provides a per-tab, in-memory store
// scoped to the user's session. The follow-up change moves authoritative
// state to a server-side DynamoDB table per Cognito sub.

"use client"

import { useEffect, useState, useSyncExternalStore } from "react"

export type Order = {
  id: string
  patientId: string
  patientName?: string
  procedureCode?: string
  procedureName?: string
  payorName?: string
  status?: string
  paStatus?: string
  priorAuthRequired?: boolean
  decision?: string
  evidence?: Record<string, any>
  createdAt: string
  updatedAt?: string
  [key: string]: any
}

const _store: Map<string, Order> = new Map()
const _listeners = new Set<() => void>()

function subscribe(listener: () => void) {
  _listeners.add(listener)
  return () => {
    _listeners.delete(listener)
  }
}

function notify() {
  for (const listener of _listeners) listener()
}

function snapshot(): Order[] {
  return Array.from(_store.values()).sort((a, b) =>
    (b.updatedAt ?? b.createdAt).localeCompare(a.updatedAt ?? a.createdAt)
  )
}

// Stable empty array reference for SSR / pre-hydration.
const EMPTY: Order[] = []

/**
 * React hook returning the current orders list. Fully in-memory; orders are
 * lost on tab close. This is intentional — see Threat T12.
 */
export function useOrders(): Order[] {
  return useSyncExternalStore(subscribe, snapshot, () => EMPTY)
}

export function getOrder(id: string): Order | undefined {
  return _store.get(id)
}

export function getOrders(): Order[] {
  return snapshot()
}

export function upsertOrder(order: Order) {
  _store.set(order.id, {
    ...order,
    updatedAt: new Date().toISOString(),
  })
  notify()
}

export function updateOrder(id: string, patch: Partial<Order>) {
  const existing = _store.get(id)
  if (!existing) return
  _store.set(id, { ...existing, ...patch, updatedAt: new Date().toISOString() })
  notify()
}

export function clearOrders() {
  _store.clear()
  notify()
}

/**
 * One-time migration helper: on app start, evict any legacy ``pa_orders``
 * entries that lived in localStorage. Called from app/layout.tsx so older
 * sessions stop leaking PHI to disk.
 */
export function evictLegacyOrdersFromLocalStorage() {
  if (typeof window === "undefined") return
  try {
    window.localStorage.removeItem("pa_orders")
  } catch {
    // ignore
  }
}

/**
 * Convenience hook: same as useOrders but also runs the legacy eviction once.
 */
export function useOrdersWithMigration(): Order[] {
  const [migrated, setMigrated] = useState(false)
  useEffect(() => {
    if (!migrated) {
      evictLegacyOrdersFromLocalStorage()
      setMigrated(true)
    }
  }, [migrated])
  return useOrders()
}
