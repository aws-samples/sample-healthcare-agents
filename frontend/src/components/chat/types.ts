// Define message types
export type MessageRole = "user" | "assistant"

export interface Message {
  role: MessageRole
  content: string
  timestamp: string
}

// Define chat session types
export interface ChatSession {
  id: string
  name: string
  history: Message[]
  startDate: string
  endDate: string
}