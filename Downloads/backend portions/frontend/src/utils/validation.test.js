import { describe, expect, it } from 'vitest'
import {
  validateImageFile,
  validateClaim,
  isSafeHttpUrl,
  truncate,
  MAX_IMAGE_BYTES,
} from './validation.js'

/** Client-side input validation & sanitisation (Part C.2) and URL allow-listing (Part C.5). */

const file = (name, type, size) => ({ name, type, size })

describe('validateImageFile — type and size are checked BEFORE upload', () => {
  it('accepts a valid jpg / png / webp under 8 MB', () => {
    expect(validateImageFile(file('a.jpg', 'image/jpeg', 1024)).ok).toBe(true)
    expect(validateImageFile(file('a.png', 'image/png', 2048)).ok).toBe(true)
    expect(validateImageFile(file('a.webp', 'image/webp', 4096)).ok).toBe(true)
  })

  it('rejects non-image types', () => {
    const res = validateImageFile(file('notes.txt', 'text/plain', 100))
    expect(res.ok).toBe(false)
    expect(res.error).toMatch(/Unsupported file type/)
  })

  it('rejects a text file disguised with an image extension (MIME wins)', () => {
    const res = validateImageFile(file('payload.png', 'text/plain', 100))
    expect(res.ok).toBe(false)
  })

  it('rejects oversized images and reports both sizes in the message', () => {
    const res = validateImageFile(file('big.png', 'image/png', MAX_IMAGE_BYTES + 1))
    expect(res.ok).toBe(false)
    expect(res.error).toMatch(/too large/)
    expect(res.error).toMatch(/8\.0 MB/)
  })

  it('accepts exactly 8 MB (boundary)', () => {
    expect(validateImageFile(file('edge.png', 'image/png', MAX_IMAGE_BYTES)).ok).toBe(true)
  })

  it('rejects an empty file', () => {
    expect(validateImageFile(file('zero.png', 'image/png', 0)).ok).toBe(false)
  })

  it('rejects a missing file', () => {
    expect(validateImageFile(null).ok).toBe(false)
  })
})

describe('validateClaim — mirrors the backend 10–1000 rule', () => {
  it('rejects claims shorter than 10 characters', () => {
    const res = validateClaim('too short')
    expect(res.ok).toBe(false)
    expect(res.error).toMatch(/at least 10/)
  })

  it('rejects claims longer than 1000 characters', () => {
    const res = validateClaim('a'.repeat(1001))
    expect(res.ok).toBe(false)
    expect(res.error).toMatch(/too long/)
  })

  it('accepts a normal claim and trims it', () => {
    const res = validateClaim('   The Eiffel Tower was built in 1889.   ')
    expect(res.ok).toBe(true)
    expect(res.value).toBe('The Eiffel Tower was built in 1889.')
  })

  it('collapses whitespace so a claim cannot forge multi-line log entries', () => {
    const res = validateClaim('A claim long enough\n[ADMIN] approved\tthe transfer\r\n')
    expect(res.ok).toBe(true)
    expect(res.value).not.toMatch(/[\n\r\t]/)
    expect(res.value).toMatch(/A claim long enough \[ADMIN\] approved the transfer/)
  })

  it('strips zero-width characters (used to evade keyword filters)', () => {
    const res = validateClaim('A claim with zero\u200Bwidth\uFEFF characters inside it')
    expect(res.ok).toBe(true)
    expect(res.value).not.toMatch(/[\u200B\uFEFF]/)
  })
})

describe('isSafeHttpUrl — the href allow-list behind SafeLink (Part C.5)', () => {
  it('allows http and https', () => {
    expect(isSafeHttpUrl('https://reuters.com/article')).toBe(true)
    expect(isSafeHttpUrl('http://example.org')).toBe(true)
  })

  it('BLOCKS javascript: URLs — the XSS vector React escaping cannot stop', () => {
    expect(isSafeHttpUrl('javascript:alert(document.cookie)')).toBe(false)
  })

  it('blocks data:, vbscript: and file: URLs', () => {
    expect(isSafeHttpUrl('data:text/html,<script>alert(1)</script>')).toBe(false)
    expect(isSafeHttpUrl('vbscript:msgbox(1)')).toBe(false)
    expect(isSafeHttpUrl('file:///etc/passwd')).toBe(false)
  })

  it('blocks garbage and empty input', () => {
    expect(isSafeHttpUrl('')).toBe(false)
    expect(isSafeHttpUrl(null)).toBe(false)
    expect(isSafeHttpUrl('not a url at all')).toBe(false)
  })
})

describe('truncate', () => {
  it('shortens long text and appends an ellipsis', () => {
    expect(truncate('a'.repeat(200), 140)).toHaveLength(140)
    expect(truncate('a'.repeat(200), 140).endsWith('…')).toBe(true)
  })

  it('leaves short text untouched', () => {
    expect(truncate('hello', 140)).toBe('hello')
  })
})
