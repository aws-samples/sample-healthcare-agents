"use client"

import React, { useEffect, useState, useCallback } from "react"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Button } from "@/components/ui/button"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Loader2, AlertCircle, CheckCircle, FileText } from "lucide-react"

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface QuestionnaireItem {
  linkId: string
  text?: string
  type: string
  required?: boolean
  answerOption?: Array<{ valueCoding?: { code: string; display?: string; system?: string }; valueString?: string }>
  item?: QuestionnaireItem[]
  extension?: Array<{ url: string; valueExpression?: { language: string; expression: string } }>
}

interface FHIRQuestionnaire {
  resourceType: "Questionnaire"
  id?: string
  url?: string
  title?: string
  status: string
  item?: QuestionnaireItem[]
}

interface AutoFillResult {
  linkId: string
  sourceResourceId: string | null
  resolvedValue: unknown
  expressionType: string
}

interface QuestionnaireResponseItem {
  linkId: string
  text?: string
  answer?: Array<Record<string, unknown>>
}

interface FHIRQuestionnaireResponse {
  resourceType: "QuestionnaireResponse"
  status: "completed"
  questionnaire: string
  subject?: { reference: string }
  authored: string
  item: QuestionnaireResponseItem[]
}

interface DTRQuestionnaireRendererProps {
  questionnaireUrl: string
  patientId: string
  onSubmit: (response: FHIRQuestionnaireResponse) => void
  onCancel?: () => void
  autoFillResults?: AutoFillResult[]
  fetchQuestionnaire?: (url: string) => Promise<FHIRQuestionnaire>
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function buildTypedAnswer(type: string, value: string): Record<string, unknown> | null {
  if (!value && value !== "false") return null
  switch (type) {
    case "string":
    case "text":
      return { valueString: value }
    case "integer":
      return { valueInteger: parseInt(value, 10) }
    case "decimal":
    case "quantity":
      return { valueDecimal: parseFloat(value) }
    case "boolean":
      return { valueBoolean: value === "true" }
    case "date":
      return { valueDate: value }
    case "choice":
      return { valueCoding: { code: value } }
    default:
      return { valueString: value }
  }
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function DTRQuestionnaireRenderer({
  questionnaireUrl,
  patientId,
  onSubmit,
  onCancel,
  autoFillResults = [],
  fetchQuestionnaire,
}: DTRQuestionnaireRendererProps) {
  const [questionnaire, setQuestionnaire] = useState<FHIRQuestionnaire | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [answers, setAnswers] = useState<Record<string, string>>({})
  const [autoFilledIds, setAutoFilledIds] = useState<Set<string>>(new Set())
  const [validationErrors, setValidationErrors] = useState<Record<string, string>>({})

  // Fetch questionnaire on mount
  useEffect(() => {
    let cancelled = false
    async function load() {
      setLoading(true)
      setError(null)
      try {
        let q: FHIRQuestionnaire
        if (fetchQuestionnaire) {
          q = await fetchQuestionnaire(questionnaireUrl)
        } else {
          const res = await fetch(questionnaireUrl, {
            headers: { Accept: "application/fhir+json" },
          })
          if (!res.ok) throw new Error(`HTTP ${res.status}`)
          q = await res.json()
        }
        if (q.resourceType !== "Questionnaire") throw new Error("Invalid resource type")
        if (!cancelled) setQuestionnaire(q)
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Failed to load questionnaire")
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [questionnaireUrl, fetchQuestionnaire])

  // Apply auto-fill results
  useEffect(() => {
    if (!questionnaire || autoFillResults.length === 0) return
    const filled: Record<string, string> = {}
    const ids = new Set<string>()
    for (const r of autoFillResults) {
      if (r.resolvedValue != null) {
        filled[r.linkId] = String(r.resolvedValue)
        ids.add(r.linkId)
      }
    }
    setAnswers(prev => ({ ...prev, ...filled }))
    setAutoFilledIds(ids)
  }, [questionnaire, autoFillResults])

  const setAnswer = useCallback((linkId: string, value: string) => {
    setAnswers(prev => ({ ...prev, [linkId]: value }))
    setValidationErrors(prev => {
      const next = { ...prev }
      delete next[linkId]
      return next
    })
  }, [])

  const validate = useCallback((): boolean => {
    if (!questionnaire?.item) return true
    const errors: Record<string, string> = {}
    const checkItems = (items: QuestionnaireItem[]) => {
      for (const item of items) {
        if (item.required && (!answers[item.linkId] || answers[item.linkId].trim() === "")) {
          errors[item.linkId] = "This field is required"
        }
        if (item.item) checkItems(item.item)
      }
    }
    checkItems(questionnaire.item)
    setValidationErrors(errors)
    return Object.keys(errors).length === 0
  }, [questionnaire, answers])

  const handleSubmit = useCallback(() => {
    if (!questionnaire || !validate()) return

    const buildResponseItems = (items: QuestionnaireItem[]): QuestionnaireResponseItem[] => {
      const result: QuestionnaireResponseItem[] = []
      for (const item of items) {
        const val = answers[item.linkId]
        const typed = val != null ? buildTypedAnswer(item.type, val) : null
        const responseItem: QuestionnaireResponseItem = {
          linkId: item.linkId,
          text: item.text,
        }
        if (typed) responseItem.answer = [typed]
        if (item.item) {
          const nested = buildResponseItems(item.item)
          if (nested.length > 0) (responseItem as any).item = nested
        }
        result.push(responseItem)
      }
      return result
    }

    const response: FHIRQuestionnaireResponse = {
      resourceType: "QuestionnaireResponse",
      status: "completed",
      questionnaire: questionnaire.url || questionnaireUrl,
      subject: { reference: `Patient/${patientId}` },
      authored: new Date().toISOString(),
      item: buildResponseItems(questionnaire.item || []),
    }
    onSubmit(response)
  }, [questionnaire, answers, validate, onSubmit, patientId, questionnaireUrl])

  // Render a single questionnaire item as the appropriate form control
  const renderItem = (item: QuestionnaireItem, depth = 0) => {
    const isAutoFilled = autoFilledIds.has(item.linkId)
    const hasError = !!validationErrors[item.linkId]
    const value = answers[item.linkId] ?? ""

    const label = (
      <div className="flex items-center gap-2 mb-1">
        <label htmlFor={`q-${item.linkId}`} className="text-sm font-medium text-gray-700">
          {item.text || item.linkId}
          {item.required && <span className="text-red-500 ml-1" aria-label="required">*</span>}
        </label>
        {isAutoFilled && (
          <span className="text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full">
            Auto-filled from EHR
          </span>
        )}
      </div>
    )

    let control: React.ReactNode
    switch (item.type) {
      case "string":
        control = (
          <Input
            id={`q-${item.linkId}`}
            type="text"
            value={value}
            onChange={e => setAnswer(item.linkId, e.target.value)}
            aria-required={item.required}
            aria-invalid={hasError}
          />
        )
        break
      case "text":
        control = (
          <Textarea
            id={`q-${item.linkId}`}
            value={value}
            onChange={e => setAnswer(item.linkId, e.target.value)}
            rows={3}
            aria-required={item.required}
            aria-invalid={hasError}
          />
        )
        break
      case "boolean":
        control = (
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              id={`q-${item.linkId}`}
              type="checkbox"
              checked={value === "true"}
              onChange={e => setAnswer(item.linkId, e.target.checked ? "true" : "false")}
              className="h-4 w-4 rounded border-gray-300"
              aria-required={item.required}
              aria-invalid={hasError}
            />
            <span className="text-sm text-gray-600">Yes</span>
          </label>
        )
        break
      case "choice":
        control = (
          <Select value={value} onValueChange={v => setAnswer(item.linkId, v)}>
            <SelectTrigger id={`q-${item.linkId}`} aria-required={item.required} aria-invalid={hasError}>
              <SelectValue placeholder="Select..." />
            </SelectTrigger>
            <SelectContent>
              {(item.answerOption || []).map((opt, i) => {
                const code = opt.valueCoding?.code || opt.valueString || `opt-${i}`
                const display = opt.valueCoding?.display || opt.valueString || code
                return <SelectItem key={code} value={code}>{display}</SelectItem>
              })}
            </SelectContent>
          </Select>
        )
        break
      case "date":
        control = (
          <Input
            id={`q-${item.linkId}`}
            type="date"
            value={value}
            onChange={e => setAnswer(item.linkId, e.target.value)}
            aria-required={item.required}
            aria-invalid={hasError}
          />
        )
        break
      case "integer":
        control = (
          <Input
            id={`q-${item.linkId}`}
            type="number"
            step="1"
            value={value}
            onChange={e => setAnswer(item.linkId, e.target.value)}
            aria-required={item.required}
            aria-invalid={hasError}
          />
        )
        break
      case "decimal":
        control = (
          <Input
            id={`q-${item.linkId}`}
            type="number"
            step="any"
            value={value}
            onChange={e => setAnswer(item.linkId, e.target.value)}
            aria-required={item.required}
            aria-invalid={hasError}
          />
        )
        break
      case "quantity":
        control = (
          <Input
            id={`q-${item.linkId}`}
            type="number"
            step="any"
            value={value}
            onChange={e => setAnswer(item.linkId, e.target.value)}
            aria-required={item.required}
            aria-invalid={hasError}
          />
        )
        break
      default:
        control = (
          <Input
            id={`q-${item.linkId}`}
            type="text"
            value={value}
            onChange={e => setAnswer(item.linkId, e.target.value)}
            aria-required={item.required}
            aria-invalid={hasError}
          />
        )
    }

    return (
      <div key={item.linkId} className={`space-y-1 ${depth > 0 ? "ml-4 pl-4 border-l-2 border-gray-200" : ""}`}>
        {label}
        {control}
        {hasError && (
          <p className="text-xs text-red-500" role="alert">{validationErrors[item.linkId]}</p>
        )}
        {item.item?.map(child => renderItem(child, depth + 1))}
      </div>
    )
  }

  // Loading state
  if (loading) {
    return (
      <Card>
        <CardContent className="flex flex-col items-center justify-center py-12 gap-3">
          <Loader2 className="h-8 w-8 animate-spin text-blue-600" />
          <p className="text-sm text-gray-600">Loading payer questionnaire...</p>
        </CardContent>
      </Card>
    )
  }

  // Error state — allow manual documentation fallback
  if (error) {
    return (
      <Card className="border-red-200">
        <CardContent className="py-8">
          <div className="flex items-start gap-3">
            <AlertCircle className="h-5 w-5 text-red-500 mt-0.5 flex-shrink-0" />
            <div>
              <p className="font-medium text-red-800">Unable to load payer questionnaire</p>
              <p className="text-sm text-gray-600 mt-1">{error}</p>
              <p className="text-sm text-gray-500 mt-2">You may proceed with manual documentation entry.</p>
              {onCancel && (
                <Button variant="outline" size="sm" className="mt-3" onClick={onCancel}>
                  Continue with manual documentation
                </Button>
              )}
            </div>
          </div>
        </CardContent>
      </Card>
    )
  }

  if (!questionnaire) return null

  return (
    <Card>
      <CardHeader className="bg-gradient-to-r from-blue-50 to-indigo-50 rounded-t-lg">
        <CardTitle className="flex items-center gap-2 text-lg">
          <FileText className="h-5 w-5 text-blue-600" />
          {questionnaire.title || "Payer Documentation Requirements"}
        </CardTitle>
        <p className="text-sm text-gray-500">
          Complete the required fields below. Auto-filled values come from the patient&apos;s EHR data.
        </p>
      </CardHeader>
      <CardContent className="pt-6 space-y-5">
        {questionnaire.item?.map(item => renderItem(item))}

        <div className="flex justify-end gap-3 pt-4 border-t">
          {onCancel && (
            <Button variant="outline" onClick={onCancel}>Cancel</Button>
          )}
          <Button onClick={handleSubmit} className="bg-blue-600 hover:bg-blue-700">
            <CheckCircle className="h-4 w-4 mr-2" /> Submit Questionnaire
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

export type { FHIRQuestionnaire, FHIRQuestionnaireResponse, QuestionnaireItem, AutoFillResult }
