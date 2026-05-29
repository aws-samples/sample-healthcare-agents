// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

/**
 * Tool Calls Panel Component
 *
 * Displays real-time tool execution tracking with parameters and results.
 * Shows a timeline of all tool calls during agent processing.
 */

import React from "react"
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card"
import { CheckCircle, Circle, Loader2, AlertCircle, ChevronDown, ChevronRight } from "lucide-react"

interface ToolCall {
  id: string
  name: string
  status: "pending" | "executing" | "completed" | "failed"
  parameters?: Record<string, any>
  result?: any
  error?: string
  timestamp: string
  specialist?: string  // Name of specialist agent (if tool called by specialist)
}

interface ToolCallsPanelProps {
  toolCalls: ToolCall[]
}

function ToolCallItem({ toolCall }: { toolCall: ToolCall }) {
  const [expanded, setExpanded] = React.useState(false)

  const statusIcon = () => {
    switch (toolCall.status) {
      case "pending":
        return <Circle className="w-4 h-4 text-gray-400" />
      case "executing":
        return <Loader2 className="w-4 h-4 text-blue-500 animate-spin" />
      case "completed":
        return <CheckCircle className="w-4 h-4 text-green-500" />
      case "failed":
        return <AlertCircle className="w-4 h-4 text-red-500" />
    }
  }

  const statusColor = () => {
    switch (toolCall.status) {
      case "pending":
        return "border-gray-200 bg-gray-50"
      case "executing":
        return "border-blue-200 bg-blue-50"
      case "completed":
        return "border-green-200 bg-green-50"
      case "failed":
        return "border-red-200 bg-red-50"
    }
  }

  const formatToolName = (name: string) => {
    // Convert snake_case to Title Case
    return name
      .split("_")
      .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
      .join(" ")
  }

  return (
    <div className={`border rounded-lg p-3 ${statusColor()} transition-all`}>
      <div className="flex items-start gap-3">
        {statusIcon()}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h4 className="font-medium text-sm">{formatToolName(toolCall.name)}</h4>
            {toolCall.specialist && (
              <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-purple-100 text-purple-800">
                {toolCall.specialist}
              </span>
            )}
            <span className="text-xs text-gray-500">
              {new Date(toolCall.timestamp).toLocaleTimeString()}
            </span>
          </div>

          {/* Parameters & Results Toggle */}
          {(toolCall.parameters || toolCall.result || toolCall.error) && (
            <button
              onClick={() => setExpanded(!expanded)}
              className="mt-1 flex items-center gap-1 text-xs text-gray-600 hover:text-gray-900"
            >
              {expanded ? (
                <ChevronDown className="w-3 h-3" />
              ) : (
                <ChevronRight className="w-3 h-3" />
              )}
              {expanded ? "Hide" : "Show"} details
            </button>
          )}

          {/* Expanded Details */}
          {expanded && (
            <div className="mt-2 space-y-2 text-xs">
              {toolCall.parameters && Object.keys(toolCall.parameters).length > 0 && (
                <div>
                  <div className="font-semibold text-gray-700 mb-1">Parameters:</div>
                  <pre className="bg-white p-2 rounded border text-xs overflow-x-auto">
                    {JSON.stringify(toolCall.parameters, null, 2)}
                  </pre>
                </div>
              )}

              {toolCall.result && (
                <div>
                  <div className="font-semibold text-gray-700 mb-1">Result:</div>
                  <pre className="bg-white p-2 rounded border text-xs overflow-x-auto max-h-40">
                    {typeof toolCall.result === "string"
                      ? toolCall.result
                      : JSON.stringify(toolCall.result, null, 2)}
                  </pre>
                </div>
              )}

              {toolCall.error && (
                <div>
                  <div className="font-semibold text-red-700 mb-1">Error:</div>
                  <div className="bg-white p-2 rounded border text-red-600">{toolCall.error}</div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export function ToolCallsPanel({ toolCalls }: ToolCallsPanelProps) {
  if (toolCalls.length === 0) {
    return null
  }

  const completedCount = toolCalls.filter((t) => t.status === "completed").length
  const executingCount = toolCalls.filter((t) => t.status === "executing").length
  const failedCount = toolCalls.filter((t) => t.status === "failed").length

  return (
    <Card className="mb-4">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base">Tool Execution Timeline</CardTitle>
          <div className="flex items-center gap-3 text-xs">
            {executingCount > 0 && (
              <span className="flex items-center gap-1 text-blue-600">
                <Loader2 className="w-3 h-3 animate-spin" />
                {executingCount} executing
              </span>
            )}
            {completedCount > 0 && (
              <span className="flex items-center gap-1 text-green-600">
                <CheckCircle className="w-3 h-3" />
                {completedCount} completed
              </span>
            )}
            {failedCount > 0 && (
              <span className="flex items-center gap-1 text-red-600">
                <AlertCircle className="w-3 h-3" />
                {failedCount} failed
              </span>
            )}
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <div className="space-y-2">
          {toolCalls.map((toolCall) => (
            <ToolCallItem key={toolCall.id} toolCall={toolCall} />
          ))}
        </div>
      </CardContent>
    </Card>
  )
}
