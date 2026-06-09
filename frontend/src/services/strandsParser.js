// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

/**
 * Strands Agent Streaming Parser
 *
 * This parser processes Server-Sent Events (SSE) from Strands agents that use
 * the Amazon Bedrock Converse API format. Strands agents wrap their responses
 * in nested event structures.
 *
 * EVENTS HANDLED:
 * 1. Status Events - Structured progress events from agent processing
 *    Format: {"status": "CLASSIFIED", "event_id": "evt_123", ...}
 *    Action: Calls statusCallback with status update (doesn't add to text)
 *
 * 2. messageStart - Signals the beginning of a new assistant message
 *    Format: {"event": {"messageStart": {"role": "assistant"}}}
 *    Action: Adds newline separator between messages
 *
 * 3. contentBlockDelta - Contains incremental text content
 *    Format: {"event": {"contentBlockDelta": {"delta": {"text": "Hello"}}}}
 *    Action: Appends text to the completion stream
 */

/**
 * Parse a streaming chunk from a Strands agent.
 *
 * @param {string} line - The SSE line to parse
 * @param {string} currentCompletion - The accumulated completion text
 * @param {Function} updateCallback - Callback to update the UI with new text
 * @param {Function} statusCallback - Callback to handle status events (optional)
 * @returns {string} Updated completion text
 */
export const parseStreamingChunk = (line, currentCompletion, updateCallback, statusCallback = null) => {
  // Skip empty lines
  if (!line || !line.trim()) {
    return currentCompletion;
  }

  // Strip "data: " prefix from SSE format
  if (!line.startsWith('data: ')) {
    return currentCompletion;
  }

  const data = line.substring(6).trim();

  // Skip empty data
  if (!data) {
    return currentCompletion;
  }

  // Parse JSON events
  try {
    const json = JSON.parse(data);

    // Handle tool call start - contentBlockStart with toolUse
    // Example: {"event": {"contentBlockStart": {"start": {"toolUse": {"toolUseId": "...", "name": "..."}}}}}
    if (json.event?.contentBlockStart?.start?.toolUse) {
      const toolUse = json.event.contentBlockStart.start.toolUse;
      if (statusCallback) {
        statusCallback({
          type: 'tool_call_start',
          toolCallId: toolUse.toolUseId,
          toolName: toolUse.name,
          timestamp: new Date().toISOString()
        });
      }
      return currentCompletion;
    }

    // Handle tool call parameters - contentBlockDelta with toolUse
    // Example: {"event": {"contentBlockDelta": {"delta": {"toolUse": {"input": "..."}}}}}
    if (json.event?.contentBlockDelta?.delta?.toolUse?.input) {
      const input = json.event.contentBlockDelta.delta.toolUse.input;
      if (statusCallback) {
        statusCallback({
          type: 'tool_call_input',
          input: input,
          timestamp: new Date().toISOString()
        });
      }
      return currentCompletion;
    }

    // Handle tool call completion - contentBlockStop
    // Example: {"event": {"contentBlockStop": {"contentBlockIndex": 0}}}
    if (json.event?.contentBlockStop) {
      if (statusCallback) {
        statusCallback({
          type: 'tool_call_complete',
          timestamp: new Date().toISOString()
        });
      }
      return currentCompletion;
    }

    // Handle tool results - messageStart with toolResult role
    // Example: {"event": {"messageStart": {"role": "user"}}} followed by tool result content
    if (json.event?.messageStart?.role === 'user') {
      // This might be a tool result message
      return currentCompletion;
    }

    // Handle status events (new for structured progress updates)
    // Example: {"status": "CLASSIFIED", "event_id": "evt_123", "classification": {...}}
    if (json.status) {
      if (statusCallback) {
        statusCallback({
          type: 'status',
          status: json.status,
          data: json
        });
      }
      // Don't add status events to text completion
      return currentCompletion;
    }

    // Handle specialist tool start events
    // Example: {"type": "specialist_tool_start", "specialist": "MedicationSafety", "tool_name": "check_drug_database", ...}
    if (json.type === 'specialist_tool_start') {
      if (statusCallback) {
        statusCallback({
          type: 'tool_call_start',
          toolCallId: json.tool_call_id,
          toolName: json.tool_name,
          specialist: json.specialist,
          timestamp: json.timestamp
        });
      }
      return currentCompletion;
    }

    // Handle specialist tool result events
    // Example: {"type": "specialist_tool_result", "specialist": "MedicationSafety", "tool_name": "check_drug_database", "result": {...}}
    if (json.type === 'specialist_tool_result') {
      if (statusCallback) {
        statusCallback({
          type: 'tool_call_result',
          toolCallId: json.tool_call_id,
          result: json.result,
          specialist: json.specialist,
          timestamp: json.timestamp
        });
      }
      return currentCompletion;
    }

    // Handle message start - add newline for new assistant message
    // Example: {"event": {"messageStart": {"role": "assistant"}}}
    if (json.event?.messageStart?.role === 'assistant') {
      if (currentCompletion) {  // Only add newline if there's previous content
        const newCompletion = currentCompletion + '\n\n';
        updateCallback(newCompletion);
        return newCompletion;
      }
      return currentCompletion;
    }

    // Extract streaming text from contentBlockDelta event
    // Example: {"event": {"contentBlockDelta": {"delta": {"text": " there"}}}}
    if (json.event?.contentBlockDelta?.delta?.text) {
      let textContent = json.event.contentBlockDelta.delta.text;

      // Check if the text looks like a JSON response from the safety agent
      if (textContent.trim().startsWith('{') && textContent.includes('"statusCode"')) {
        try {
          const parsedResponse = JSON.parse(textContent);
          if (parsedResponse.body) {
            const bodyContent = JSON.parse(parsedResponse.body);
            if (bodyContent.result?.analysis) {
              updateCallback(bodyContent.result.analysis);
              return bodyContent.result.analysis;
            }
          }
        } catch (e) {
          // If parsing fails, just use the text as-is
          console.debug('Failed to parse JSON from text content');
        }
      }

      const newCompletion = currentCompletion + textContent;
      updateCallback(newCompletion);
      return newCompletion;
    }

    // Handle tool response with embedded JSON (safety agent format)
    // Example: {"event": {"contentBlockDelta": {"delta": {"toolUse": {...}}}}}
    if (json.event?.contentBlockDelta?.delta?.toolUse?.content) {
      const toolContent = json.event.contentBlockDelta.delta.toolUse.content;

      // Notify about tool result if callback provided
      if (statusCallback) {
        statusCallback({
          type: 'tool_call_result',
          result: toolContent,
          timestamp: new Date().toISOString()
        });
      }

      try {
        // If it's a string, try to parse as JSON
        if (typeof toolContent === 'string') {
          const toolResult = JSON.parse(toolContent);
          // Extract analysis from the response body
          if (toolResult.body) {
            const bodyContent = JSON.parse(toolResult.body);
            if (bodyContent.result?.analysis) {
              updateCallback(bodyContent.result.analysis);
              return bodyContent.result.analysis;
            }
          }
        }
      } catch (e) {
        console.debug('Failed to parse tool response:', e);
      }
    }

    // All other events are ignored (tool messages, metadata, etc.)
    return currentCompletion;
  } catch {
    // If JSON parsing fails, skip this line
    console.debug('Failed to parse streaming event:', data);
    return currentCompletion;
  }
};
