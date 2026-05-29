// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

/**
 * Status History Panel Component
 *
 * Displays a timeline of all status updates with timestamps.
 * Shows the complete processing history for hospital safety events.
 */

import React from 'react';
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card"
import { Clock } from "lucide-react"

interface StatusMetadata {
  event_id?: string;
  classification?: {
    event_type: string;
    severity: string;
    requires_immediate_action: boolean;
  };
  specialist?: string;
  alert_type?: string;
  threshold_info?: any;
  message?: string;
  timestamp?: string;
}

interface StatusEntry {
  status: string;
  metadata: StatusMetadata | null;
  timestamp: string;
}

interface StatusHistoryPanelProps {
  statusHistory: StatusEntry[];
}

const statusConfig: Record<string, { icon: string; label: string; color: string }> = {
  RECEIVED: { icon: '📥', label: 'Received', color: 'blue' },
  CLASSIFYING: { icon: '🔍', label: 'Analyzing', color: 'blue' },
  CLASSIFIED: { icon: '✓', label: 'Classified', color: 'green' },
  ROUTED: { icon: '➡️', label: 'Routed', color: 'blue' },
  ANALYZING: { icon: '⚙️', label: 'Analyzing', color: 'blue' },
  THRESHOLD_BREACHED: { icon: '⚠️', label: 'Pattern Detected', color: 'yellow' },
  ALERT_SENT: { icon: '🚨', label: 'Alert Sent', color: 'red' },
  COMPLETED: { icon: '✅', label: 'Complete', color: 'green' },
  ERROR: { icon: '❌', label: 'Error', color: 'red' }
};

const severityColors: Record<string, string> = {
  low: 'bg-gray-100 text-gray-800',
  medium: 'bg-yellow-100 text-yellow-800',
  high: 'bg-orange-100 text-orange-800',
  critical: 'bg-red-100 text-red-800'
};

function StatusItem({ entry }: { entry: StatusEntry }) {
  const config = statusConfig[entry.status] || { icon: '•', label: entry.status, color: 'gray' };
  const timestamp = new Date(entry.timestamp);

  return (
    <div className="flex items-start gap-3 p-3 border-l-2 border-gray-200 hover:bg-gray-50 transition-colors">
      {/* Timeline dot */}
      <div className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center text-lg
        ${config.color === 'blue' ? 'bg-blue-100' : ''}
        ${config.color === 'green' ? 'bg-green-100' : ''}
        ${config.color === 'yellow' ? 'bg-yellow-100' : ''}
        ${config.color === 'red' ? 'bg-red-100' : ''}
        ${config.color === 'gray' ? 'bg-gray-100' : ''}
      `}>
        {config.icon}
      </div>

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap mb-1">
          <span className="font-medium text-sm">{config.label}</span>
          <span className="flex items-center gap-1 text-xs text-gray-500">
            <Clock className="w-3 h-3" />
            {timestamp.toLocaleTimeString()}
          </span>
        </div>

        {/* Event ID */}
        {entry.metadata?.event_id && (
          <div className="text-xs text-gray-500 mb-1">
            ID: {entry.metadata.event_id}
          </div>
        )}

        {/* Classification Info */}
        {entry.metadata?.classification && (
          <div className="flex flex-wrap items-center gap-2 mt-2">
            <span className="inline-flex items-center px-2 py-1 rounded text-xs font-medium bg-purple-100 text-purple-800">
              {entry.metadata.classification.event_type.replace('_', ' ').toUpperCase()}
            </span>

            <span className={`inline-flex items-center px-2 py-1 rounded text-xs font-semibold ${
              severityColors[entry.metadata.classification.severity.toLowerCase()] || 'bg-gray-100 text-gray-800'
            }`}>
              {entry.metadata.classification.severity.toUpperCase()}
            </span>

            {entry.metadata.classification.requires_immediate_action && (
              <span className="inline-flex items-center px-2 py-1 rounded text-xs font-medium bg-red-100 text-red-800">
                ⚡ IMMEDIATE ACTION
              </span>
            )}
          </div>
        )}

        {/* Specialist Name */}
        {entry.metadata?.specialist && (
          <span className="inline-flex items-center px-2 py-1 rounded text-xs font-medium bg-indigo-100 text-indigo-800 mt-2">
            {entry.metadata.specialist}
          </span>
        )}

        {/* Alert Type */}
        {entry.metadata?.alert_type && (
          <span className="inline-flex items-center px-2 py-1 rounded text-xs font-medium bg-red-100 text-red-800 mt-2">
            Alert: {entry.metadata.alert_type.replace('_', ' ')}
          </span>
        )}

        {/* Threshold Info */}
        {entry.metadata?.threshold_info?.threshold_breached && (
          <div className="text-xs text-orange-600 font-medium mt-2">
            ⚠️ Pattern: {entry.metadata.threshold_info.event_count} events detected
          </div>
        )}
      </div>
    </div>
  );
}

export function StatusHistoryPanel({ statusHistory }: StatusHistoryPanelProps) {
  if (statusHistory.length === 0) {
    return null;
  }

  return (
    <Card className="mb-4">
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Processing Timeline</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-1">
          {statusHistory.map((entry, index) => (
            <StatusItem key={`${entry.timestamp}-${index}`} entry={entry} />
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
