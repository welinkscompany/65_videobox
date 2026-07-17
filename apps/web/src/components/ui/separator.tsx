// Source-preservation header: shadcn-ui/ui@4396d5b2a5ee4e2ad5705e9b2522f92112f811a0
// Upstream: apps/v4/registry/new-york-v4/ui/separator.tsx
// Upstream Git blob SHA-1: cd873e3631b571060f166897b7b62e033e87c18f
// License: MIT (see THIRD_PARTY_NOTICES.md)

"use client"

import * as React from "react"
import { Separator as SeparatorPrimitive } from "radix-ui"

import { cn } from "@/lib/utils"

function Separator({
  className,
  orientation = "horizontal",
  decorative = true,
  ...props
}: React.ComponentProps<typeof SeparatorPrimitive.Root>) {
  return (
    <SeparatorPrimitive.Root
      data-slot="separator"
      decorative={decorative}
      orientation={orientation}
      className={cn(
        "shrink-0 bg-border data-[orientation=horizontal]:h-px data-[orientation=horizontal]:w-full data-[orientation=vertical]:h-full data-[orientation=vertical]:w-px",
        className
      )}
      {...props}
    />
  )
}
export { Separator }
