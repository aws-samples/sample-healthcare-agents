import type { NextConfig } from "next"

const nextConfig: NextConfig = {
  distDir: "build",
  output: "export",
  typescript: {
    // Allow build to continue with TypeScript errors (they become warnings)
    ignoreBuildErrors: true,
  },
}

export default nextConfig
