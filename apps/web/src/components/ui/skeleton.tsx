// Source-preservation header: shadcn-ui/ui@4396d5b2a5ee4e2ad5705e9b2522f92112f811a0
// Upstream: apps/v4/registry/new-york-v4/ui/skeleton.tsx
// Upstream Git blob SHA-1: 3ec6be770b846170b8e7f8916e5f165e2d1730df
// License: MIT (see THIRD_PARTY_NOTICES.md)

import { cn } from "@/lib/utils"

function Skeleton({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="skeleton"
      className={cn("animate-pulse rounded-md bg-accent", className)}
      {...props}
    />
  )
}
export { Skeleton }
