// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

/**
 * ProcessingStatus Component
 *
 * Displays real-time processing status for hospital safety events.
 * Shows structured progress updates at each stage of the analysis workflow.
 */

import React from 'react';

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

interface ProcessingStatusProps {
  status: string | null;
  metadata?: StatusMetadata | null;
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

export function ProcessingStatus({ status, metadata }: ProcessingStatusProps) {
  if (!status) {
    return null;
  }

  const config = statusConfig[status];

  if (!config) {
    return null;
  }

  return (
    <div className="flex flex-wrap items-center gap-2 px-4 py-2 bg-gray-50 border-b border-gray-200">
      {/* Status Badge */}
      <span className={`inline-flex items-center px-3 py-1 rounded-full text-sm font-medium
        ${config.color === 'blue' ? 'bg-blue-100 text-blue-800' : ''}
        ${config.color === 'green' ? 'bg-green-100 text-green-800' : ''}
        ${config.color === 'yellow' ? 'bg-yellow-100 text-yellow-800' : ''}
        ${config.color === 'red' ? 'bg-red-100 text-red-800' : ''}
      `}>
        <span className="mr-1">{config.icon}</span>
        {config.label}
      </span>

      {/* Event ID */}
      {metadata?.event_id && (
        <span className="text-xs text-gray-500">
          ID: {metadata.event_id}
        </span>
      )}

      {/* Classification Info */}
      {metadata?.classification && (
        <>
          <span className="inline-flex items-center px-2 py-1 rounded text-xs font-medium bg-purple-100 text-purple-800">
            {metadata.classification.event_type.replace('_', ' ').toUpperCase()}
          </span>

          <span className={`inline-flex items-center px-2 py-1 rounded text-xs font-semibold ${
            severityColors[metadata.classification.severity.toLowerCase()] || 'bg-gray-100 text-gray-800'
          }`}>
            {metadata.classification.severity.toUpperCase()}
          </span>

          {metadata.classification.requires_immediate_action && (
            <span className="inline-flex items-center px-2 py-1 rounded text-xs font-medium bg-red-100 text-red-800">
              ⚡ IMMEDIATE ACTION
            </span>
          )}
        </>
      )}

      {/* Specialist Name */}
      {metadata?.specialist && (
        <span className="inline-flex items-center px-2 py-1 rounded text-xs font-medium bg-indigo-100 text-indigo-800">
          {metadata.specialist}
        </span>
      )}

      {/* Alert Type */}
      {metadata?.alert_type && (
        <span className="inline-flex items-center px-2 py-1 rounded text-xs font-medium bg-red-100 text-red-800">
          Alert: {metadata.alert_type.replace('_', ' ')}
        </span>
      )}

      {/* Threshold Info */}
      {metadata?.threshold_info?.threshold_breached && (
        <span className="text-xs text-orange-600 font-medium">
          ⚠️ Pattern: {metadata.threshold_info.event_count} events detected
        </span>
      )}

      {/* Loading Spinner for In-Progress States */}
      {['CLASSIFYING', 'ANALYZING'].includes(status) && (
        <svg
          className="animate-spin h-4 w-4 text-blue-500"
          xmlns="http://www.w3.org/2000/svg"
          fill="none"
          viewBox="0 0 24 24"
        >
          <circle
            className="opacity-25"
            cx="12"
            cy="12"
            r="10"
            stroke="currentColor"
            strokeWidth="4"
          />
          <path
            className="opacity-75"
            fill="currentColor"
            d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
          />
        </svg>
      )}
    </div>
  );
}
