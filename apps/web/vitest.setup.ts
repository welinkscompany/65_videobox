import "@testing-library/jest-dom/vitest";
import { installNetworkGuard } from "./src/lib/network-guard"

installNetworkGuard()

// jsdom intentionally does not implement media playback. Components still need
// to exercise their stop/recovery paths without turning a passing suite noisy.
Object.defineProperty(HTMLMediaElement.prototype, "pause", { configurable: true, value: () => undefined })
Object.defineProperty(HTMLMediaElement.prototype, "play", { configurable: true, value: () => Promise.resolve() })
