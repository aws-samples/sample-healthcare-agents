import { AuthProvider } from "@/components/auth/AuthProvider"
import { LegacyStorageEviction } from "@/components/auth/LegacyStorageEviction"
import { PatientContextProvider } from "@/app/context/PatientContext"
import type { Metadata } from "next"
import { Geist, Geist_Mono } from "next/font/google"
import "./globals.css"

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
})

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
})

export const metadata: Metadata = {
  title: "Fullstack AgentCore Solution Template",
  description: "A solution template for building GenAI applications with AgentCore",
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="en">
      <body className={`${geistSans.variable} ${geistMono.variable} antialiased`}>
        <LegacyStorageEviction />
        <AuthProvider>
          <PatientContextProvider>{children}</PatientContextProvider>
        </AuthProvider>
      </body>
    </html>
  )
}
