// Source-preservation header: shadcn-ui/ui@4396d5b2a5ee4e2ad5705e9b2522f92112f811a0
// Upstream: apps/v4/registry/new-york-v4/lib/utils.ts
// Upstream Git blob SHA-1: bd0c391ddd1088e9067844c48835bf4abcd61783
// License: MIT (see THIRD_PARTY_NOTICES.md)

import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
