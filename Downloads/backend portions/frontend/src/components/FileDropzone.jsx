import { useCallback, useRef, useState } from 'react'
import { validateImageFile, formatBytes, MAX_IMAGE_BYTES, ALLOWED_IMAGE_EXT } from '../utils/validation.js'

/**
 * FileDropzone — drag & drop / click-to-browse image picker.
 *
 * SECURITY (Part C.2 — Input validation before upload):
 *   `accept` on the <input> is only a filter hint in the file dialog; it does NOT
 *   stop a user choosing "All files". The real check is validateImageFile(),
 *   which enforces MIME type and the 8 MB ceiling *before* a single byte leaves
 *   the browser. This gives instant feedback and avoids wasting GPU inference
 *   time and bandwidth on requests the backend would reject anyway.
 *
 * SECURITY (safe previews):
 *   The preview uses URL.createObjectURL(file) — a blob: URL that points at the
 *   local File object. We never inject the file's bytes into the DOM and never
 *   use dangerouslySetInnerHTML, so an uploaded SVG/HTML payload cannot execute.
 *   (SVG isn't even an accepted type here.) Object URLs are revoked on
 *   unmount / replacement to avoid a memory leak.
 */
export default function FileDropzone({ file, onFileChange, onError, disabled }) {
  const inputRef = useRef(null)
  const [dragging, setDragging] = useState(false)
  const [previewUrl, setPreviewUrl] = useState(null)

  const acceptFile = useCallback(
    (candidate) => {
      if (!candidate) return
      const check = validateImageFile(candidate)
      if (!check.ok) {
        onError?.(check.error)
        onFileChange(null)
        setPreviewUrl(null)
        return
      }
      onError?.(null)
      onFileChange(candidate)
      setPreviewUrl((old) => {
        if (old) URL.revokeObjectURL(old)
        return URL.createObjectURL(candidate)
      })
    },
    [onError, onFileChange],
  )

  function handleDrop(e) {
    e.preventDefault()
    setDragging(false)
    if (disabled) return

    // SECURITY: a drop can carry many files, and files can be dragged from
    // another window. We take exactly one, and only if it validates.
    const dropped = e.dataTransfer?.files?.[0]
    if (e.dataTransfer?.files?.length > 1) {
      onError?.('Please drop a single image at a time.')
      return
    }
    acceptFile(dropped)
  }

  function clear() {
    onFileChange(null)
    setPreviewUrl((old) => {
      if (old) URL.revokeObjectURL(old)
      return null
    })
    onError?.(null)
    if (inputRef.current) inputRef.current.value = ''
  }

  return (
    <div>
      <div
        role="button"
        tabIndex={0}
        aria-label="Upload an image for deepfake detection"
        onClick={() => !disabled && inputRef.current?.click()}
        onKeyDown={(e) => {
          if (!disabled && (e.key === 'Enter' || e.key === ' ')) {
            e.preventDefault()
            inputRef.current?.click()
          }
        }}
        onDragOver={(e) => {
          e.preventDefault()
          if (!disabled) setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        className={`relative rounded-card border-2 border-dashed transition duration-200 cursor-pointer
          ${dragging ? 'border-teal bg-teal/10 scale-[1.01]' : 'border-navy-border bg-navy hover:border-teal/50'}
          ${disabled ? 'opacity-60 cursor-not-allowed' : ''}
          ${previewUrl ? 'p-4' : 'p-10 sm:p-14'} text-center`}
      >
        <input
          ref={inputRef}
          type="file"
          accept="image/jpeg,image/png,image/webp"
          className="hidden"
          disabled={disabled}
          onChange={(e) => acceptFile(e.target.files?.[0])}
        />

        {previewUrl ? (
          <div className="flex flex-col sm:flex-row items-center gap-4">
            <img
              src={previewUrl}
              alt="Selected upload preview"
              className="max-h-56 w-auto rounded border border-navy-border object-contain bg-navy-card"
            />
            <div className="text-left flex-1 min-w-0">
              {/* Filename is user-controlled -> rendered as escaped text only. */}
              <p className="text-ink font-medium truncate" title={file?.name}>
                {file?.name}
              </p>
              <p className="text-xs text-ink-muted mt-1">
                {file ? formatBytes(file.size) : ''} · {file?.type || 'image'}
              </p>
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation()
                  clear()
                }}
                className="btn-ghost !py-1.5 !px-3 text-xs mt-3"
                disabled={disabled}
              >
                Remove image
              </button>
            </div>
          </div>
        ) : (
          <>
            <div className="mx-auto w-14 h-14 grid place-items-center rounded-full bg-teal/10 border border-teal/25 text-2xl">
              🖼️
            </div>
            <p className="mt-4 text-ink font-medium">
              Drag &amp; drop an image here, or <span className="text-teal">browse</span>
            </p>
            <p className="text-xs text-ink-muted mt-2">
              {ALLOWED_IMAGE_EXT.join(', ').toUpperCase()} · max {formatBytes(MAX_IMAGE_BYTES)}
            </p>
            <p className="text-[11px] text-ink-muted/70 mt-3">
              Validated in your browser before upload — nothing is sent until you press Analyse.
            </p>
          </>
        )}
      </div>
    </div>
  )
}
