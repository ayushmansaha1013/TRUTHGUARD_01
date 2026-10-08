import { useEffect, useState } from 'react'
import { onCooldownChange } from '../services/api.js'

/**
 * useRateLimitCooldown — Part C.3 (Rate Limiting Awareness)
 *
 * Returns { locked, remainingSeconds } where `locked` is true while the client
 * is in its post-429 cooldown. Pages use it to disable the submit button and
 * show "Please wait a moment before trying again".
 *
 * WHY CLIENT-SIDE: it costs nothing, it is instantly demonstrable, and it stops
 * the most common real-world cause of 429s — a user clicking again because the
 * spinner made them think nothing happened. It is a UX guard, not a security
 * boundary: server-side rate limiting remains mandatory.
 */
export function useRateLimitCooldown() {
  const [until, setUntil] = useState(0)
  const [, forceTick] = useState(0)

  useEffect(() => onCooldownChange(setUntil), [])

  // Re-render once per second while locked so the countdown is visible.
  useEffect(() => {
    if (!until || Date.now() >= until) return undefined
    const id = setInterval(() => forceTick((n) => n + 1), 1000)
    return () => clearInterval(id)
  }, [until])

  const remainingMs = Math.max(0, until - Date.now())

  return {
    locked: remainingMs > 0,
    remainingSeconds: Math.ceil(remainingMs / 1000),
  }
}

export default useRateLimitCooldown
