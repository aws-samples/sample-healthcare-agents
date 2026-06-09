"use client"

import { createContext, PropsWithChildren, useContext, useState } from "react"

interface GlobalContextType {
  thingOne: string
  setThingOne: (value: string) => void
  isLoading: boolean
  setIsLoading: (loading: boolean) => void
}

const GlobalContext = createContext<GlobalContextType | undefined>(undefined)

export function GlobalContextProvider({ children }: PropsWithChildren) {
  const [thingOne, setThingOne] = useState("")
  const [isLoading, setIsLoading] = useState(false)

  return (
    <GlobalContext.Provider
      value={{
        thingOne,
        setThingOne,
        isLoading,
        setIsLoading,
      }}
    >
      {children}
    </GlobalContext.Provider>
  )
}

export function useGlobal() {
  const context = useContext(GlobalContext)
  if (context === undefined) {
    throw new Error("useGlobal must be used within a GlobalContext")
  }
  return context
}
