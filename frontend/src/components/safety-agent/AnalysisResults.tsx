// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

/**
 * Analysis Results Component
 *
 * Displays the safety analysis results in a formatted, easy-to-read layout.
 */

import React from "react"
import { AlertCircle } from "lucide-react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"

interface AnalysisResultsProps {
  content: string
}

export function AnalysisResults({ content }: AnalysisResultsProps) {
  if (!content) {
    return (
      <div className="flex items-center justify-center h-96 text-gray-400">
        <div className="text-center">
          <AlertCircle className="w-12 h-12 mx-auto mb-4 opacity-50" />
          <p>Submit an incident report to see analysis results</p>
        </div>
      </div>
    )
  }

  return (
    <div className="bg-white rounded-lg h-[600px] overflow-y-auto">
      <div className="prose prose-sm max-w-none p-6
        prose-headings:font-bold
        prose-h1:text-2xl prose-h1:mb-4 prose-h1:text-gray-900
        prose-h2:text-xl prose-h2:mb-3 prose-h2:mt-6 prose-h2:pb-2 prose-h2:border-b-2 prose-h2:border-gray-200 prose-h2:text-gray-900
        prose-h3:text-lg prose-h3:mb-2 prose-h3:mt-4 prose-h3:text-gray-800
        prose-p:text-gray-700 prose-p:mb-2 prose-p:leading-relaxed
        prose-strong:text-gray-900 prose-strong:font-semibold
        prose-ul:my-2 prose-ul:list-disc prose-ul:pl-6
        prose-ol:my-2 prose-ol:list-decimal prose-ol:pl-6
        prose-li:text-gray-700 prose-li:mb-1
        prose-code:text-purple-600 prose-code:bg-purple-50 prose-code:px-1 prose-code:py-0.5 prose-code:rounded prose-code:text-sm
        prose-pre:bg-gray-100 prose-pre:border prose-pre:border-gray-300 prose-pre:rounded-lg prose-pre:p-4
        prose-blockquote:border-l-4 prose-blockquote:border-blue-500 prose-blockquote:pl-4 prose-blockquote:italic prose-blockquote:text-gray-600
        prose-hr:border-gray-300 prose-hr:my-4
        prose-table:border-collapse prose-table:w-full
        prose-th:bg-gray-100 prose-th:border prose-th:border-gray-300 prose-th:px-4 prose-th:py-2 prose-th:text-left
        prose-td:border prose-td:border-gray-300 prose-td:px-4 prose-td:py-2
        prose-a:text-blue-600 prose-a:underline hover:prose-a:text-blue-800"
      >
        <ReactMarkdown remarkPlugins={[remarkGfm]}>
          {content}
        </ReactMarkdown>
      </div>
    </div>
  )
}
