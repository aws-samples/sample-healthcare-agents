// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

/**
 * Safety Agent Screen Component
 *
 * Dedicated interface for reporting and analyzing hospital safety incidents.
 */

"use client"

import React, { useState } from "react"
import { useRouter } from "next/navigation"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { AnalysisResults } from "./AnalysisResults"
import { ToolCallsPanel } from "./ToolCallsPanel"
import { StatusHistoryPanel } from "./StatusHistoryPanel"
import { ArrowLeft, Send, AlertCircle, FileText } from "lucide-react"
import { useAuth } from "react-oidc-context"
import { invokeAgentCore, generateSessionId } from "@/services/agentCoreService"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"

const SAFETY_EVENT_EXAMPLES = {
  patient_fall: {
    label: "Patient Fall Event",
    text: `COMPREHENSIVE SAFETY EVENT REPORT - PATIENT FALL

Event Date: January 29, 2026 at 3:15 AM
Event Classification: Adverse Event

Patient Information:
- Medical Record Number: MRN-452891
- Patient ID: Room 405, Bed B
- Age: 82 years old female (Older adult category)
- Clinical State: Post-operative day 3 following hip replacement, taking pain medications, slightly disoriented

Event Type: Patient Fall

Timeline of Events:
- 03:00 AM - Patient last checked by nursing staff, sleeping
- 03:15 AM - Patient attempted to get to bathroom without assistance
- 03:17 AM - Found on floor by Nurse Martinez during rounds
- 03:18 AM - Rapid response called
- 03:25 AM - Physician Dr. Johnson arrived at bedside
- 03:30 AM - X-ray ordered stat
- 04:15 AM - X-ray results showed hip fracture

Equipment Involved:
- Hospital bed with adjustable rails (Model: Hill-Rom Advance)
- Call button system (not within reach)
- Non-slip socks (patient not wearing at time of fall)
- Patient mobility alarm (was silenced earlier in shift)

Contributing Root Causes:
- Bed rails were down (patient request for comfort)
- Call button out of reach on bedside table
- Patient confused about post-operative mobility restrictions
- Inadequate lighting in room at night
- Nurse-to-patient ratio high (1:8) during night shift
- Mobility alarm silenced due to frequent false alarms

Immediate Actions Taken:
- Nurse Martinez responded immediately and assessed injuries
- Patient kept on floor, not moved until physician assessment
- Vital signs taken and monitored
- Physician Dr. Johnson notified and arrived within 7 minutes
- Stat X-ray ordered and completed
- Pain medication (Morphine 4mg IV) administered
- Family contacted and updated
- Incident report filed in safety system
- Patient transferred to radiology via stretcher

Patient Harm Assessment:
- Harm Level: Permanent harm
- Left hip fracture confirmed on X-ray
- Severe pain 9/10 on pain scale
- Unable to bear weight on left leg
- Bruising on left arm and hip
- Required surgical intervention (ORIF procedure)
- Extended hospital stay by 5-7 days
- Increased fall risk going forward

Staff Involved:
- Nurse Martinez (RN, discovered patient, 8 years experience)
- Dr. Johnson (attending orthopedic surgeon)
- Nurse Chen (supervisor, responded to incident)
- Radiology technician Williams

Location: Medical-Surgical Unit 4B, Room 405

This incident requires immediate review of fall prevention protocols, bed rail policies, call button placement standards, and nurse staffing ratios during night shifts.`
  },
  medication_error: {
    label: "Medication Error",
    text: `COMPREHENSIVE SAFETY EVENT REPORT - MEDICATION ERROR

Event Date: January 30, 2026 at 10:20 AM
Event Classification: Adverse Event

Patient Information:
- Medical Record Number: MRN-789456
- Patient ID: Room 508, Bed A
- Age: 67 years old (Adult age category)
- Clinical State: Post-operative day 2 following cardiac surgery, vital signs stable but patient confused and disoriented

Event Type: Medication Error - Wrong Dose Administration

Timeline of Events:
- 08:00 AM - Physician ordered Heparin 5,000 units subcutaneous injection for DVT prophylaxis
- 09:30 AM - Order entered into electronic system by Unit Secretary
- 10:15 AM - Medication retrieved from Pyxis automated dispensing cabinet by Nurse Johnson
- 10:20 AM - Heparin 50,000 units (10x prescribed dose) administered to patient
- 11:45 AM - Error discovered during medication reconciliation by Pharmacist Lee
- 11:50 AM - Physician Dr. Smith notified immediately
- 12:00 PM - Protamine sulfate antidote administered

Equipment and Medications Involved:
- Pyxis MedStation ES automated dispensing cabinet (Unit 3B)
- Heparin sodium injection 10,000 units/mL vial
- BD SafetyGlide needle and syringe
- Protamine sulfate 50mg vial (antidote)
- Coagulation monitoring equipment (PT/INR machine)

Contributing Root Causes:
- Look-alike vial presentation (5,000 vs 50,000 units similar packaging)
- Nurse fatigue - end of 12-hour night shift
- Barcode scanning bypassed due to system downtime
- Communication breakdown - verbal order not double-checked
- Inadequate lighting in medication preparation area
- Training gap - new nurse orientation incomplete on high-alert medications

Immediate Actions Taken:
- Rapid response team activated
- Protamine sulfate antidote administered within 10 minutes
- Continuous cardiac monitoring initiated
- Serial coagulation studies ordered (PT, PTT, INR every 2 hours)
- Patient and family notified and counseled
- Incident report filed in safety system
- Medication order placed on hold pending review
- Pharmacy director and chief medical officer notified

Patient Harm Assessment:
- Harm Level: Temporary harm
- Patient developed minor bleeding from IV site
- INR elevated to 4.5 (therapeutic range 2.0-3.0)
- No major bleeding complications observed
- Full recovery expected with antidote treatment
- Extended monitoring required for 24 hours
- Harm assessed: Within 24 hours of discovery

Rescue Intervention: Yes - Protamine sulfate antidote administered to reverse anticoagulation

Patient/Family Notification: Yes - Patient and family immediately notified and counseled about the error

Increased Length of Stay: Yes - Extended monitoring for 24 hours required due to medication error

Staff Involved:
- Nurse Johnson (RN, 6 months experience)
- Pharmacist Lee (discovered error)
- Dr. Smith (attending physician)
- Nurse Martinez (supervisor, responded to incident)

Location: Medical-Surgical Unit 3B, Room 508

This incident requires immediate system-level review and implementation of additional safety measures including mandatory barcode scanning, enhanced high-alert medication protocols, and fatigue management policies.`
  },
  infection_control: {
    label: "Infection Control Breach",
    text: `COMPREHENSIVE SAFETY EVENT REPORT - INFECTION CONTROL BREACH

Event Date: January 28, 2026 at 2:30 PM
Event Classification: Unsafe Condition

Patient Information:
- Medical Record Number: MRN-445623
- Patient ID: Room 312, Bed B
- Age: 52 years old female
- Clinical State: Post-surgical (knee replacement day 3), stable, recovering well

Event Type: Infection Control - Contaminated Medical Equipment

Timeline of Events:
- 02:00 PM - Routine infection control audit began on Medical-Surgical Unit
- 02:30 PM - Infection control nurse found blood pressure cuffs not cleaned between patients
- 02:35 PM - Five contaminated BP cuffs identified (visible soil, not disinfected)
- 02:40 PM - All contaminated equipment removed from service immediately
- 02:45 PM - Unit manager and charge nurse notified
- 03:00 PM - All patients who had contact with contaminated equipment identified (8 patients)
- 03:15 PM - Risk assessment completed for each patient
- 03:30 PM - Physicians notified for all affected patients

Equipment Involved:
- Five Welch Allyn blood pressure cuffs (Models: FlexiPort reusable cuffs)
- Cleaning wipes (CaviWipes disinfectant - available but not used)
- Equipment cleaning log (incomplete documentation)
- Wall-mounted cleaning protocol signage (present)

Contributing Root Causes:
- Staff time constraints during high patient census periods
- Lack of clear accountability for equipment cleaning between patients
- Incomplete training on equipment disinfection protocols
- No visual indicator system for clean vs. dirty equipment
- Equipment cleaning log not consistently maintained
- Insufficient supervision during busy shifts

Immediate Actions Taken:
- All five contaminated cuffs removed from patient care areas
- Contaminated equipment sent for terminal cleaning
- All 8 affected patients assessed for signs of infection
- Physicians notified and surveillance cultures considered
- Replacement blood pressure cuffs deployed with clean/dirty tags
- Staff emergency education session scheduled for next shift
- Infection prevention team conducted immediate unit rounds
- Incident reports filed for all affected patients

Patient Harm Assessment:
- Harm Level: None (no infections detected)
- All 8 patients assessed - no signs of cross-contamination
- No elevated temperatures or infection symptoms
- Enhanced monitoring initiated for 7 days
- No antibiotics required at this time
- Follow-up assessments scheduled

Staff Involved:
- Nurse Martinez (infection control nurse, discovered during audit)
- Unit Manager Johnson
- Charge Nurse Williams
- 8 bedside nurses who used contaminated equipment
- Environmental services supervisor

Location: Medical-Surgical Unit 3, Multiple patient rooms

This incident highlights gaps in equipment cleaning protocols and the need for enhanced staff education, clear accountability systems, and visual management tools to prevent cross-contamination between patients.`
  },
  device_malfunction: {
    label: "Device Malfunction",
    text: `COMPREHENSIVE SAFETY EVENT REPORT - DEVICE MALFUNCTION

Event Date: January 27, 2026 at 3:18 AM

Patient Information:
- Medical Record Number: MRN-998877
- Patient ID: ICU Room 310, Bed 2
- Age: 45 years old female
- Clinical State: Septic shock requiring vasopressor support, mechanically ventilated, hemodynamically unstable

Event Type: Medical Device Malfunction - IV Pump Failure

Timeline of Events:
- 02:30 AM - IV infusion pump programmed for norepinephrine 8 mcg/min
- 03:15 AM - Pump alarm "upstream occlusion" sounded
- 03:16 AM - Nurse attempted to silence and troubleshoot alarm
- 03:18 AM - Pump malfunction - delivered bolus of norepinephrine over 30 seconds
- 03:19 AM - Patient blood pressure spiked to 220/110 mmHg (from baseline 95/60)
- 03:20 AM - Bedside nurse recognized pump malfunction and disconnected
- 03:21 AM - Physician notified and responded immediately
- 03:25 AM - Manual IV administration initiated with new pump
- 03:45 AM - Blood pressure stabilized at 105/65 mmHg

Equipment Involved:
- Baxter Sigma Spectrum IV infusion pump (Model: 35700BAX, Serial: SS45789)
- Norepinephrine infusion 16 mg in 250 mL D5W
- IV tubing set (primary line)
- Central venous catheter (subclavian)
- Hemodynamic monitoring equipment (arterial line)

Contributing Root Causes:
- Equipment malfunction - pump software error during alarm state
- Pump overdue for preventive maintenance (last service 8 months ago)
- Biomedical engineering understaffed (3 month backlog on scheduled maintenance)
- Nurse unfamiliar with this specific pump malfunction pattern
- High-alert medication without independent double-check
- No smart pump dose limits configured for norepinephrine bolus

Immediate Actions Taken:
- Pump immediately disconnected and tagged out of service
- Patient blood pressure managed with antihypertensive (labetalol 10mg IV)
- Continuous arterial blood pressure monitoring
- EKG performed to rule out cardiac ischemia
- Neurological assessment for stroke symptoms
- New pump brought to bedside and medication restarted
- Biomedical engineering notified stat
- Pump sent to biomedical engineering for forensic analysis
- Incident report filed immediately
- Family updated on event

Patient Harm Assessment:
- Harm Level: Temporary harm
- Severe hypertensive episode (220/110 mmHg)
- Patient developed severe headache
- Transient chest discomfort (troponin negative)
- No evidence of stroke on neurological exam
- No cardiac ischemia on EKG or cardiac enzymes
- Blood pressure normalized within 25 minutes
- Full recovery expected, but required extended monitoring

Staff Involved:
- Nurse Rodriguez (RN, ICU, discovered malfunction, 4 years experience)
- Dr. Patel (ICU intensivist, responded to event)
- Biomedical engineering technician Brown
- Charge Nurse Davis (notified and coordinated response)

Location: Intensive Care Unit, Room 310

This incident requires immediate device safety review, enhanced preventive maintenance scheduling, staff training on high-risk device alarms, and implementation of smart pump safety protocols for vasoactive medications.`
  }
}

export function SafetyAgentScreen() {
  const router = useRouter()
  const auth = useAuth()
  const [sessionId] = useState(() => generateSessionId())

  const [incidentText, setIncidentText] = useState("")
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<string>("")

  // Track status history with timestamps
  const [statusHistory, setStatusHistory] = useState<Array<{
    status: string
    metadata: any
    timestamp: string
  }>>([])

  // Track tool calls
  const [toolCalls, setToolCalls] = useState<Array<{
    id: string
    name: string
    status: "pending" | "executing" | "completed" | "failed"
    parameters?: Record<string, any>
    result?: any
    error?: string
    timestamp: string
    specialist?: string
  }>>([])
  const currentToolCallRef = React.useRef<{id: string, name: string, input: string, specialist?: string} | null>(null)

  const handleSubmit = async () => {
    if (!incidentText.trim()) {
      setError("Please enter a safety incident description")
      return
    }

    setError(null)
    setResult("")
    setStatusHistory([])
    setToolCalls([])
    currentToolCallRef.current = null
    setIsSubmitting(true)

    try {
      const accessToken = auth.user?.access_token
      const userId = auth.user?.profile?.sub

      if (!accessToken || !userId) {
        throw new Error("Authentication required. Please log in again.")
      }

      await invokeAgentCore(
        incidentText,
        sessionId,
        (streamedContent: string) => {
          console.log('Streamed content:', streamedContent)
          setResult(streamedContent)
        },
        accessToken,
        userId,
        (statusUpdate: { type: string; status?: string; data?: any; toolCallId?: string; toolName?: string; input?: string; result?: any; timestamp?: string; specialist?: string }) => {
          console.log('Status update:', statusUpdate)

          // Handle regular status updates
          if (statusUpdate.type === 'status') {
            // Add to status history with timestamp
            setStatusHistory(prev => [...prev, {
              status: statusUpdate.status!,
              metadata: statusUpdate.data,
              timestamp: new Date().toISOString()
            }])

            // If COMPLETED status has analysis in the data, extract it
            if (statusUpdate.status === 'COMPLETED' && statusUpdate.data?.analysis) {
              setResult(statusUpdate.data.analysis)
            }
          }

          // Handle tool call start
          if (statusUpdate.type === 'tool_call_start') {
            const newToolCall = {
              id: statusUpdate.toolCallId!,
              name: statusUpdate.toolName!,
              status: 'executing' as const,
              timestamp: statusUpdate.timestamp!,
              specialist: statusUpdate.specialist  // Include specialist name if present
            }
            currentToolCallRef.current = {
              id: statusUpdate.toolCallId!,
              name: statusUpdate.toolName!,
              input: '',
              specialist: statusUpdate.specialist
            }
            setToolCalls(prev => [...prev, newToolCall])
          }

          // Handle tool call input
          if (statusUpdate.type === 'tool_call_input' && currentToolCallRef.current) {
            currentToolCallRef.current.input += statusUpdate.input || ''
          }

          // Handle tool call completion
          if (statusUpdate.type === 'tool_call_complete' && currentToolCallRef.current) {
            const currentTool = currentToolCallRef.current
            setToolCalls(prev => prev.map(tool =>
              tool.id === currentTool.id
                ? {
                    ...tool,
                    status: 'completed' as const,
                    parameters: currentTool.input ? JSON.parse(currentTool.input) : undefined
                  }
                : tool
            ))
            currentToolCallRef.current = null
          }

          // Handle tool call result
          if (statusUpdate.type === 'tool_call_result') {
            setToolCalls(prev => {
              // Find the matching tool call by ID and specialist
              const matchingTool = [...prev].reverse().find(t =>
                t.id === statusUpdate.toolCallId &&
                t.specialist === statusUpdate.specialist &&
                !t.result
              )
              if (matchingTool) {
                return prev.map(tool =>
                  tool.id === matchingTool.id && tool.specialist === matchingTool.specialist
                    ? { ...tool, result: statusUpdate.result, status: 'completed' as const }
                    : tool
                )
              }
              return prev
            })
          }
        }
      )
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : "Unknown error"
      setError(`Failed to analyze incident: ${errorMessage}`)
      console.error("Error invoking safety agent:", err)
    } finally {
      setIsSubmitting(false)
    }
  }

  const [selectedExample, setSelectedExample] = useState<string>("")

  const handleUseExample = (exampleKey: string) => {
    if (exampleKey && SAFETY_EVENT_EXAMPLES[exampleKey as keyof typeof SAFETY_EVENT_EXAMPLES]) {
      setIncidentText(SAFETY_EVENT_EXAMPLES[exampleKey as keyof typeof SAFETY_EVENT_EXAMPLES].text)
      setSelectedExample(exampleKey)
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-b from-gray-50 to-gray-100">
      {/* Header */}
      <div className="bg-white shadow-sm border-b">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex items-center gap-4">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => router.push("/")}
              className="gap-2"
            >
              <ArrowLeft className="w-4 h-4" />
              Back to Agents
            </Button>
            <div className="flex-1">
              <h1 className="text-2xl font-bold text-gray-900">Hospital Safety Agent</h1>
              <p className="text-sm text-gray-600">Report and analyze patient safety incidents</p>
            </div>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Status History Panel */}
        <StatusHistoryPanel statusHistory={statusHistory} />

        {/* Tool Calls Panel */}
        <ToolCallsPanel toolCalls={toolCalls} />
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Input Section */}
          <Card>
            <CardHeader>
              <CardTitle>Report Safety Incident</CardTitle>
              <CardDescription>
                Enter details about the safety incident including patient information, incident description, and response actions
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <textarea
                  value={incidentText}
                  onChange={(e) => setIncidentText(e.target.value)}
                  placeholder="Describe the safety incident..."
                  className="w-full h-96 p-4 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none font-mono text-sm"
                  disabled={isSubmitting}
                />
              </div>

              <div className="space-y-3">
                <div className="flex gap-2 items-center">
                  <FileText className="w-4 h-4 text-gray-500" />
                  <span className="text-sm font-medium text-gray-700">Load Example:</span>
                  <Select
                    value={selectedExample}
                    onValueChange={handleUseExample}
                    disabled={isSubmitting}
                  >
                    <SelectTrigger className="flex-1">
                      <SelectValue placeholder="Choose a safety event example..." />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="patient_fall">
                        {SAFETY_EVENT_EXAMPLES.patient_fall.label}
                      </SelectItem>
                      <SelectItem value="medication_error">
                        {SAFETY_EVENT_EXAMPLES.medication_error.label}
                      </SelectItem>
                      <SelectItem value="infection_control">
                        {SAFETY_EVENT_EXAMPLES.infection_control.label}
                      </SelectItem>
                      <SelectItem value="device_malfunction">
                        {SAFETY_EVENT_EXAMPLES.device_malfunction.label}
                      </SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <Button
                  onClick={handleSubmit}
                  disabled={isSubmitting || !incidentText.trim()}
                  className="w-full gap-2"
                >
                  {isSubmitting ? (
                    <>
                      <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                      Analyzing...
                    </>
                  ) : (
                    <>
                      <Send className="w-4 h-4" />
                      Analyze Incident
                    </>
                  )}
                </Button>
              </div>

              {error && (
                <div className="flex items-center gap-2 p-3 bg-red-50 border border-red-200 rounded-lg">
                  <AlertCircle className="w-5 h-5 text-red-600" />
                  <p className="text-sm text-red-700">{error}</p>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Results Section */}
          <Card>
            <CardHeader>
              <CardTitle>Analysis Results</CardTitle>
              <CardDescription>
                Comprehensive safety analysis with recommendations
              </CardDescription>
            </CardHeader>
            <CardContent>
              <AnalysisResults content={result} />
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
