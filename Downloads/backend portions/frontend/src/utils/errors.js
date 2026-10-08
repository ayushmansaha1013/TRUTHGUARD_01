/**
 * ---------------------------------------------------------------------------
 * Error mapping — turns raw HTTP/backend failures into human-readable messages
 * ---------------------------------------------------------------------------
 * The FastAPI backend answers errors as { "detail": "...", "error_code": "..." }
 * with 400 / 413 / 422 / 429 / 502 / 503 / 504. A student user should never see
 * a stack trace or a raw "502" — they should see what to do next.
 */

/**
 * Decide whether a thrown value is an HTTP Response or a transport-level failure.
 *
 * WHY DUCK-TYPING INSTEAD OF `instanceof Response`:
 *   `fetch` rejections are TypeErrors, while HTTP errors come back as Response
 *   objects — we must tell them apart to produce the right message. But
 *   `instanceof` compares constructor identity, which breaks whenever a Response
 *   crosses a realm boundary (iframes, workers, SSR, or a test harness that
 *   resets the module registry). Checking for the shape we actually use
 *   (`status` + `clone`) is both more robust and more honest about intent.
 */
function looksLikeResponse(value) {
  return (
    !!value &&
    typeof value === 'object' &&
    typeof value.status === 'number' &&
    typeof value.clone === 'function'
  )
}

/** Thrown for every API failure so callers can `instanceof ApiError`. */
export class ApiError extends Error {
  constructor(message, { status = 0, code = 'unknown', retryable = false } = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.retryable = retryable
  }
}

const MESSAGES = {
  400: { msg: 'That request was rejected as invalid. Please check your input and try again.', retryable: false },
  401: { msg: 'Your session has expired. Please sign in again.', retryable: false },
  403: { msg: 'You do not have permission to run this analysis.', retryable: false },
  413: { msg: 'The file is too large. The maximum size is 8 MB.', retryable: false },
  422: { msg: 'The AI service could not understand that input. Please rephrase or re-upload.', retryable: false },
  429: { msg: 'Too many requests. Please wait a moment before trying again.', retryable: true },
  500: { msg: 'The detection service hit an internal error. Please try again shortly.', retryable: true },
  502: { msg: 'The AI model is starting up or unreachable (gateway error). Try again in ~30 seconds.', retryable: true },
  503: { msg: 'The detection service is temporarily unavailable or overloaded. Please retry shortly.', retryable: true },
  504: { msg: 'The analysis timed out. The model may be cold-starting — please try again.', retryable: true },
}

/**
 * Convert a fetch Response (or a network TypeError) into an ApiError.
 */
export async function toApiError(errOrResponse) {
  // Network failure / CORS / DNS / backend completely down -> fetch throws a
  // TypeError and there is no Response to inspect at all.
  if (!looksLikeResponse(errOrResponse)) {
    return new ApiError(
      'Could not reach the TruthGuard AI service. Check your internet connection and try again.',
      { status: 0, code: 'network_error', retryable: true },
    )
  }

  const res = errOrResponse
  let detail = ''
  let code = ''

  try {
    const body = await res.clone().json()
    if (body && typeof body === 'object') {
      // FastAPI validation errors return `detail` as an array of objects.
      if (Array.isArray(body.detail)) {
        detail = body.detail.map((d) => d?.msg).filter(Boolean).join(' ')
      } else if (typeof body.detail === 'string') {
        detail = body.detail
      } else if (typeof body.message === 'string') {
        detail = body.message
      }
      code = typeof body.error_code === 'string' ? body.error_code : ''
    }
  } catch {
    /* non-JSON error body (HTML proxy page, empty 504, etc.) — fall through */
  }

  const mapped = MESSAGES[res.status]
  const message =
    detail && detail.length < 240
      ? detail
      : mapped?.msg ?? `Request failed with status ${res.status}.`

  return new ApiError(message, {
    status: res.status,
    code: code || `http_${res.status}`,
    retryable: mapped?.retryable ?? res.status >= 500,
  })
}

/** Small helper for the UI: is this a "try again later" class of failure? */
export function isRateLimited(error) {
  return error?.status === 429 || error?.code === 'rate_limited'
}
