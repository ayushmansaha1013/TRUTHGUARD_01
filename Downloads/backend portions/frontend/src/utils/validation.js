/**
 * ---------------------------------------------------------------------------
 * Client-side input validation & sanitisation — Part C.2
 * ---------------------------------------------------------------------------
 * WHY THIS MATTERS (for the project report):
 *   Client-side validation is a UX + cost control, NOT a security control.
 *   It gives instant feedback ("file too large") instead of a 3-second round
 *   trip and a 413 error, and it stops obviously-bad requests from consuming
 *   expensive GPU inference time on the backend.
 *   It can always be bypassed (curl / Postman), so the FastAPI backend MUST
 *   independently validate the same constraints. Defence in depth: the browser
 *   check is layer 1, Pydantic/FastAPI validation is layer 2.
 */

export const ALLOWED_IMAGE_MIME = ['image/jpeg', 'image/png', 'image/webp']
export const ALLOWED_IMAGE_EXT = ['.jpg', '.jpeg', '.png', '.webp']
export const MAX_IMAGE_BYTES = 8 * 1024 * 1024 // 8 MB — mirrors the backend limit
export const CLAIM_MIN = 10
export const CLAIM_MAX = 1000

/** Format bytes as a human readable string for error messages. */
export function formatBytes(bytes) {
  if (bytes === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  const i = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1)
  return `${(bytes / 1024 ** i).toFixed(i === 0 ? 0 : 1)} ${units[i]}`
}

/**
 * Validate an image File BEFORE it is uploaded.
 * @returns {{ ok: boolean, error?: string }}
 */
export function validateImageFile(file) {
  if (!file) return { ok: false, error: 'No file selected.' }

  // 1) MIME type check — the browser's own detection (spoofable, hence layer 2
  //    on the backend, which should also sniff magic bytes).
  const name = String(file.name || '').toLowerCase()
  const hasGoodExt = ALLOWED_IMAGE_EXT.some((ext) => name.endsWith(ext))
  const hasGoodMime = ALLOWED_IMAGE_MIME.includes(file.type)

  if (!hasGoodMime && !hasGoodExt) {
    return {
      ok: false,
      error: 'Unsupported file type. Please upload a JPG, PNG or WEBP image.',
    }
  }
  // Catch the classic "payload.txt renamed to payload.png" trick: if the browser
  // reports a MIME type at all and it is not an image, reject it.
  if (file.type && !hasGoodMime) {
    return { ok: false, error: 'That file is not a valid JPG, PNG or WEBP image.' }
  }

  // 2) Size check — prevents a 413 from the server / gateway and wasted bandwidth.
  if (file.size > MAX_IMAGE_BYTES) {
    return {
      ok: false,
      error: `Image is too large (${formatBytes(file.size)}). The maximum size is ${formatBytes(MAX_IMAGE_BYTES)}.`,
    }
  }
  if (file.size === 0) {
    return { ok: false, error: 'That file is empty. Please choose a real image.' }
  }

  return { ok: true }
}

/**
 * Validate a fact-check claim. Mirrors the backend's 10–1000 character rule.
 * We also reject control characters, which are never legitimate in a claim and
 * are a common ingredient in log-injection / terminal-escape attacks.
 * @returns {{ ok: boolean, error?: string, value?: string }}
 */
export function validateClaim(raw) {
  // SECURITY (sanitisation): trim + strip zero-width and C0/C1 control chars.
  // This keeps the value that gets *logged* into scan_logs clean, so a crafted
  // claim can't forge log lines or break the educator dashboard table.
  const value = String(raw ?? '')
    // eslint-disable-next-line no-control-regex
    .replace(/[\u0000-\u001F\u007F-\u009F\u200B-\u200D\uFEFF]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()

  if (value.length < CLAIM_MIN) {
    return { ok: false, error: `Please enter at least ${CLAIM_MIN} characters (a full claim).` }
  }
  if (value.length > CLAIM_MAX) {
    return { ok: false, error: `Claim is too long (${value.length}/${CLAIM_MAX} characters). Please shorten it.` }
  }
  return { ok: true, value }
}

/**
 * SECURITY (Part C.5 — XSS prevention): URL allow-listing.
 * AI-returned "sources" are untrusted strings. React already escapes text, but a
 * URL is rendered into an <a href> — and href is one of the few places where
 * escaping does not help, because `javascript:alert(1)` is a perfectly valid,
 * fully-escaped URL that still executes when clicked.
 * We therefore only allow http/https URLs; everything else is rendered as inert
 * text (or dropped) instead of a live link.
 */
export function isSafeHttpUrl(raw) {
  try {
    const url = new URL(String(raw ?? '').trim())
    return url.protocol === 'http:' || url.protocol === 'https:'
  } catch {
    return false
  }
}

/** Truncate text for storage/display (used for scan_logs.input_summary). */
export function truncate(text, max = 140) {
  const s = String(text ?? '').trim()
  return s.length > max ? `${s.slice(0, max - 1)}…` : s
}
