"use client"

import { useEffect, useRef, useState } from "react"
import { ChatHeader } from "./ChatHeader"
import { ChatInput } from "./ChatInput"
import { ChatMessages } from "./ChatMessages"
import { ProcessingStatus } from "./ProcessingStatus"
import { Message } from "./types"

import { useGlobal } from "@/app/context/GlobalContext"
import { invokeAgentCore, generateSessionId } from "@/services/agentCoreService"
import { submitFeedback } from "@/services/feedbackService"
import { useAuth } from "react-oidc-context"

interface ChatInterfaceProps {
  title?: string
  welcomeMessage?: string
  description?: string
}

export default function ChatInterface({
  title = "Healthcare Agent",
  welcomeMessage = "How can I help you today?",
  description = "Ask a question to get started"
}: ChatInterfaceProps) {
  // State for chat messages and user input
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState("")
  const [sessionId, setSessionId] = useState(() => generateSessionId())
  const [error, setError] = useState<string | null>(null)

  // State for processing status tracking
  const [currentStatus, setCurrentStatus] = useState<string | null>(null)
  const [statusMetadata, setStatusMetadata] = useState<any>(null)

  const { isLoading, setIsLoading } = useGlobal()
  const auth = useAuth()

  // Ref for message container to enable auto-scrolling
  const messagesEndRef = useRef<HTMLDivElement>(null)

  // Note: Agent configuration is loaded by parent page component
  // (e.g., clinical-decision-support/page.tsx, safety-agent/page.tsx)
  // before ChatInterface is rendered

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    scrollToBottom()
  }, [messages])

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }

  // Send message to AgentCore backend with streaming support
  const sendMessage = async (userMessage: string) => {
    if (!userMessage.trim()) return

    // Clear any previous errors and reset status
    setError(null)
    setCurrentStatus(null)
    setStatusMetadata(null)

    // Add user message to chat
    const newUserMessage: Message = {
      role: "user",
      content: userMessage,
      timestamp: new Date().toISOString(),
    }

    setMessages((prev) => [...prev, newUserMessage])
    setInput("")
    setIsLoading(true)

    // Create placeholder for assistant response
    const assistantResponse: Message = {
      role: "assistant",
      content: "",
      timestamp: new Date().toISOString(),
    }

    setMessages((prev) => [...prev, assistantResponse])

    try {
      // Get auth tokens from react-oidc-context
      const accessToken = auth.user?.access_token
      const userId = auth.user?.profile?.email ?? auth.user?.profile?.sub

      if (!accessToken || !userId) {
        throw new Error("Authentication required. Please log in again.")
      }

      // Invoke AgentCore with streaming
      await invokeAgentCore(
        userMessage,
        sessionId,
        (streamedContent: string) => {
          // Update the last message (assistant response) with streamed content
          setMessages((prev) => {
            const updated = [...prev]
            updated[updated.length - 1] = {
              ...updated[updated.length - 1],
              content: streamedContent,
            }
            return updated
          })
        },
        accessToken,
        userId,
        (statusUpdate: { type: string; status?: string; data?: any; elicitation?: any }) => {
          // Handle OAuth elicitation
          if (statusUpdate.type === 'elicitation' && statusUpdate.elicitation) {
            console.log('[ChatInterface] OAuth elicitation received:', statusUpdate.elicitation)
            // Add elicitation to the last assistant message
            setMessages((prev) => {
              const updated = [...prev]
              const lastMessage = updated[updated.length - 1]
              if (lastMessage.role === 'assistant') {
                updated[updated.length - 1] = {
                  ...lastMessage,
                  content: lastMessage.content || 'Authorization required to complete this request.',
                  elicitation: {
                    authorizationUrl: statusUpdate.elicitation.authorizationUrl || statusUpdate.elicitation.url,
                    resourceType: statusUpdate.elicitation.resourceType || 'external resource',
                    scopes: statusUpdate.elicitation.scopes,
                    sessionUri: statusUpdate.elicitation.sessionUri
                  }
                }
              }
              return updated
            })
            return
          }

          // Handle status updates from agent processing
          if (statusUpdate.type === 'status') {
            setCurrentStatus(statusUpdate.status!)
            setStatusMetadata(statusUpdate.data)

            // Clear status when COMPLETED or ERROR
            if (statusUpdate.status === 'COMPLETED' || statusUpdate.status === 'ERROR') {
              setTimeout(() => {
                setCurrentStatus(null)
                setStatusMetadata(null)
              }, 3000) // Keep final status visible for 3 seconds
            }
          }
        }
      )
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : "Unknown error"
      setError(`Failed to get response: ${errorMessage}`)
      console.error("Error invoking AgentCore:", err)

      // Update the assistant message with error
      setMessages((prev) => {
        const updated = [...prev]
        updated[updated.length - 1] = {
          ...updated[updated.length - 1],
          content:
            "I apologize, but I encountered an error processing your request. Please try again.",
        }
        return updated
      })
    } finally {
      setIsLoading(false)
    }
  }

  // Handle form submission
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()

    sendMessage(input)
  }

  // Handle feedback submission
  const handleFeedbackSubmit = async (
    messageContent: string,
    feedbackType: "positive" | "negative",
    comment: string
  ) => {
    try {
      // Use ID token for API Gateway Cognito authorizer (not access token)
      const idToken = auth.user?.id_token

      if (!idToken) {
        throw new Error("Authentication required. Please log in again.")
      }

      await submitFeedback(
        {
          sessionId,
          message: messageContent,
          feedbackType,
          comment: comment || undefined,
        },
        idToken
      )

      console.log("Feedback submitted successfully")
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : "Unknown error"
      console.error("Error submitting feedback:", err)
      setError(`Failed to submit feedback: ${errorMessage}`)
    }
  }

  // Start a new chat by clearing messages and generating a fresh session ID.
  // A new UUID is required so the backend treats this as a distinct conversation context.
  const startNewChat = () => {
    setMessages([])
    setInput("")
    setError(null)
    setSessionId(generateSessionId())
  }

  // Check if this is the initial state (no messages)
  const isInitialState = messages.length === 0

  // Check if there are any assistant messages
  const hasAssistantMessages = messages.some((message) => message.role === "assistant")

  return (
    <div className="flex flex-col h-screen w-full">
      {/* Fixed header */}
      <div className="flex-none">
        <ChatHeader title={title} onNewChat={startNewChat} canStartNewChat={hasAssistantMessages} />
        {error && (
          <div className="bg-red-50 border-l-4 border-red-500 p-4 mx-4 mt-2">
            <p className="text-sm text-red-700">{error}</p>
          </div>
        )}
        {/* Processing status indicator */}
        {currentStatus && <ProcessingStatus status={currentStatus} metadata={statusMetadata} />}
      </div>

      {/* Conditional layout based on whether there are messages */}
      {isInitialState ? (
        // Initial state - input in the middle
        <>
          {/* Empty space above */}
          <div className="grow" />

          {/* Centered welcome message */}
          <div className="text-center mb-6">
            <h2 className="text-2xl font-bold text-gray-800">{welcomeMessage}</h2>
            <p className="text-gray-600 mt-2">{description}</p>
          </div>

          {/* Centered input */}
          <div className="px-4 mb-16 max-w-4xl mx-auto w-full">
            <ChatInput
              input={input}
              setInput={setInput}
              handleSubmit={handleSubmit}
              isLoading={isLoading}
            />
          </div>

          {/* Empty space below */}
          <div className="grow" />
        </>
      ) : (
        // Chat in progress - normal layout
        <>
          {/* Scrollable message area */}
          <div className="grow overflow-hidden">
            <div className="max-w-4xl mx-auto w-full h-full">
              <ChatMessages
                messages={messages}
                messagesEndRef={messagesEndRef}
                sessionId={sessionId}
                onFeedbackSubmit={handleFeedbackSubmit}
              />
            </div>
          </div>

          {/* Fixed input area at bottom */}
          <div className="flex-none">
            <div className="max-w-4xl mx-auto w-full">
              <ChatInput
                input={input}
                setInput={setInput}
                handleSubmit={handleSubmit}
                isLoading={isLoading}
              />
            </div>
          </div>
        </>
      )}
    </div>
  )
}
