"use client"

import { useEffect } from "react"
import { useRouter } from "next/navigation"

// Legacy route — redirect to dashboard which now has the orders list
export default function LegacyStatusPage() {
  const router = useRouter()
  useEffect(() => {
    router.replace("/")
  }, [router])
  return null
}
