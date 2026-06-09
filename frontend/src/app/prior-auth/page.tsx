"use client"

import { useEffect } from "react"
import { useRouter } from "next/navigation"

// Legacy route — redirect to new order flow
export default function LegacyPriorAuthPage() {
  const router = useRouter()
  useEffect(() => {
    router.replace("/orders/new")
  }, [router])
  return null
}
