import { createContext, useCallback, useContext, useMemo, useRef, useState } from 'react'

/**
 * Minimal toast system (no extra dependency).
 * Used for: login success, "Quiz generation coming soon", non-fatal warnings.
 */
const ToastContext = createContext(null)

const STYLES = {
  success: 'border-safe/40 bg-safe/10 text-safe',
  error: 'border-danger/40 bg-danger/10 text-danger',
  info: 'border-teal/40 bg-teal/10 text-teal',
  warn: 'border-warn/40 bg-warn/10 text-warn',
}

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])
  const idRef = useRef(0)

  const dismiss = useCallback((id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  const push = useCallback(
    (message, type = 'info', duration = 4200) => {
      const id = ++idRef.current
      setToasts((prev) => [...prev, { id, message, type }])
      if (duration > 0) setTimeout(() => dismiss(id), duration)
      return id
    },
    [dismiss],
  )

  const value = useMemo(
    () => ({
      toast: push,
      success: (m) => push(m, 'success'),
      error: (m) => push(m, 'error', 6000),
      info: (m) => push(m, 'info'),
      warn: (m) => push(m, 'warn', 6000),
    }),
    [push],
  )

  return (
    <ToastContext.Provider value={value}>
      {children}
      {/* SECURITY (Part C.5): the message is rendered as React text child, so it
          is HTML-escaped automatically. We never build toast markup from strings. */}
      <div
        className="fixed z-50 bottom-4 right-4 left-4 sm:left-auto flex flex-col gap-2 items-end pointer-events-none"
        role="status"
        aria-live="polite"
      >
        {toasts.map((t) => (
          <div
            key={t.id}
            className={`pointer-events-auto max-w-sm w-full sm:w-96 rounded-card border px-4 py-3 text-sm shadow-card bg-navy-card animate-fade-up ${
              STYLES[t.type] ?? STYLES.info
            }`}
          >
            <div className="flex items-start gap-3">
              <span className="flex-1 break-words">{t.message}</span>
              <button
                type="button"
                onClick={() => dismiss(t.id)}
                className="text-ink-muted hover:text-ink transition"
                aria-label="Dismiss notification"
              >
                ✕
              </button>
            </div>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast() {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast() must be used inside <ToastProvider>')
  return ctx
}

export default ToastContext
