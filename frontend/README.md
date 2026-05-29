# Frontend - Local Development Guide

This is the React/Next.js frontend for the Fullstack AgentCore Solution Template (FAST). This README focuses on local development setup and workflows.

For full stack deployment instructions, see the [top-level README](../README.md) and [deployment documentation](../docs/DEPLOYMENT.md).

![Chat example](readme-imgs/fast-chat-screenshot.png)

## Local Development Setup

### Prerequisites

- Node.js (20+ recommended)
- npm

### Quick Start

1. Navigate to the frontend directory:

```bash
cd frontend
```

2. Install dependencies:

```bash
npm install
```

3. Start the development server:

```bash
npm run dev
```

4. Open [http://localhost:3000](http://localhost:3000) in your browser

## Development Options

### Option 1: With Authentication (Default)

By default, the app uses Cognito authentication. To test this locally:

1. First deploy the full stack (see [deployment docs](../docs/DEPLOYMENT.md))
2. Set the redirect URI for local development:

```bash
export NEXT_PUBLIC_COGNITO_REDIRECT_URI=http://localhost:3000
npm run dev
```

### Option 2: Disable Authentication (ONLY for Local Development!!!)

For faster local development without needing to deploy Cognito, you can disable authentication:

**⚠️ IMPORTANT: Remove the AuthProvider wrapper from `src/app/layout.tsx`**

Change this:

```tsx
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className={`${geistSans.variable} ${geistMono.variable} antialiased`}>
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  )
}
```

To this:

```tsx
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className={`${geistSans.variable} ${geistMono.variable} antialiased`}>{children}</body>
    </html>
  )
}
```

This bypasses all authentication flows and lets you develop the UI directly.

## UI Components

This project uses [shadcn/ui](https://ui.shadcn.com/docs/components) for UI components.

### Adding New Components

Install additional shadcn components as needed:

```bash
npx shadcn@latest add calendar
npx shadcn@latest add dialog
npx shadcn@latest add form
```

### Available Components

Browse the full component library at: https://ui.shadcn.com/docs/components

Popular components include:

- Button, Input, Textarea
- Dialog, Sheet, Popover
- Table, Card, Badge
- Form, Calendar, Select
- And many more...

## Icons

This project includes [Lucide React](https://lucide.dev/) icons, providing a comprehensive set of beautiful, customizable icons.

### Using Icons

Import and use any icon from the Lucide library:

```tsx
import { Camera } from "lucide-react"

// Usage
const App = () => {
  return <Camera color="red" size={48} />
}

export default App
```

### Available Icons

Browse all available icons at: https://lucide.dev/

Popular icons include Camera, Search, Menu, User, Settings, Download, Upload, and hundreds more.

## Project Structure

```
frontend/
├── src/
│   ├── app/                 # Next.js app router
│   ├── components/
│   │   ├── ui/             # shadcn components
│   │   └── auth/           # Authentication components
│   ├── lib/                # Utilities and configurations
│   └── services/           # API service layers
├── public/                 # Static assets
└── package.json
```

## Development Tips

- **Hot Reload**: Changes auto-reload in the browser
- **TypeScript**: Full type safety with AI assistant support
- **Tailwind CSS**: Utility-first styling
- **Vibe Coding**: Optimized for AI-assisted development

## Building with AI Assistants

This stack is designed for AI-assisted development:

1. **Describe your vision**: "Create a document upload component with drag-and-drop"
2. **Leverage shadcn components**: Rich building blocks that AI understands
3. **Iterate quickly**: Make changes and see results instantly

### Example AI Prompts

- "Add a file upload component to the chat interface"
- "Create a sidebar with navigation using shadcn components"
- "Build a settings page with form validation"
- "Add a data table with sorting and filtering"
