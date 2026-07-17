// Source-preservation header: shadcn-ui/ui@4396d5b2a5ee4e2ad5705e9b2522f92112f811a0
// Upstream: apps/v4/registry/new-york-v4/hooks/use-mobile.ts
// Upstream Git blob SHA-1: 2b0fe1dfef3b17850bbac040665f514a8ffd0f15
// License: MIT (see THIRD_PARTY_NOTICES.md)

import * as React from "react"

const MOBILE_BREAKPOINT = 768

export function useIsMobile() {
  const [isMobile, setIsMobile] = React.useState<boolean | undefined>(undefined)

  React.useEffect(() => {
    const mql = window.matchMedia(`(max-width: ${MOBILE_BREAKPOINT - 1}px)`)
    const onChange = () => {
      setIsMobile(window.innerWidth < MOBILE_BREAKPOINT)
    }
    mql.addEventListener("change", onChange)
    setIsMobile(window.innerWidth < MOBILE_BREAKPOINT)
    return () => mql.removeEventListener("change", onChange)
  }, [])

  return !!isMobile
}
