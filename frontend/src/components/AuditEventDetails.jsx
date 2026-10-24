import { useState, useEffect, useRef, useCallback } from 'react'
import { createPortal } from 'react-dom'
import { Check, Copy, ChevronDown, ChevronUp, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  auditEventSummary,
  auditFieldLabel,
} from '@/lib/audit'
import { formatBytes } from '@/lib/documents'
import { cn } from '@/lib/utils'

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
const HEX_PATTERN = /^[0-9a-f]{16,}$/i
const ISO_DATE_PATTERN = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/

function CopyValueButton({ text, label = 'Copy value' }) {
  const [copied, setCopied] = useState(false)

  async function handleCopy(e) {
    e.stopPropagation()
    try {
      await navigator.clipboard.writeText(String(text))
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      setCopied(false)
    }
  }

  return (
    <button
      type="button"
      onClick={handleCopy}
      className="inline-flex items-center text-muted-foreground hover:text-foreground transition-colors p-0.5 rounded ml-1.5 focus:outline-none focus:ring-1 focus:ring-ring"
      title={copied ? 'Copied!' : label}
      aria-label={copied ? 'Copied to clipboard' : label}
    >
      {copied ? <Check className="size-3 text-emerald-600" /> : <Copy className="size-3" />}
    </button>
  )
}

function ScalarValue({ value }) {
  if (typeof value === 'boolean') {
    return <span className="font-medium">{value ? 'Yes' : 'No'}</span>
  }
  if (value === null || value === undefined) {
    return <span className="text-muted-foreground italic">Not recorded</span>
  }

  const text = String(value)
  const isTechnical =
    UUID_PATTERN.test(text) || HEX_PATTERN.test(text) || ISO_DATE_PATTERN.test(text)

  return (
    <span className="inline-flex items-baseline flex-wrap">
      <span
        className={
          isTechnical
            ? 'font-mono text-[11px] break-all select-all text-slate-800 bg-slate-100/80 px-1 py-0.5 rounded'
            : 'break-words text-xs'
        }
      >
        {text}
      </span>
      {isTechnical && text.length > 8 ? <CopyValueButton text={text} /> : null}
    </span>
  )
}

function MetadataScalar({ field, value }) {
  if (value === null || value === undefined || value === '') {
    return <span className="text-muted-foreground italic">Not recorded</span>
  }

  const text = String(value)
  const needsCopy = /(^|_)(id|hash|request_id|chain_index)$/.test(field)
  return (
    <span className="flex min-w-0 items-center gap-2">
      <span
        className={cn(
          'min-w-0 break-all',
          needsCopy ? 'font-mono text-[11px]' : 'text-xs',
        )}
      >
        {text}
      </span>
      {needsCopy ? <CopyValueButton text={text} label={`Copy ${auditFieldLabel(field)}`} /> : null}
    </span>
  )
}

function FieldChangesView({ changes }) {
  if (!changes || typeof changes !== 'object') return null
  const entries = Object.entries(changes)
  if (entries.length === 0) return null

  return (
    <div className="space-y-2 rounded-md border border-border/80 bg-background/80 p-2.5 text-xs">
      <p className="font-semibold text-muted-foreground uppercase text-[10px] tracking-wider">
        Field-Level Modifications
      </p>
      <div className="space-y-2">
        {entries.map(([field, diff]) => (
          <div key={field} className="rounded border bg-muted/20 p-2 text-xs">
            <span className="font-medium text-foreground block mb-1">
              {auditFieldLabel(field)}
            </span>
            {diff && typeof diff === 'object' && ('previous' in diff || 'new' in diff) ? (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mt-1">
                <div className="rounded bg-rose-50/60 border border-rose-200/50 p-1.5 text-rose-900">
                  <span className="block text-[10px] uppercase font-semibold text-rose-700">Previous</span>
                  <span className="break-words line-through opacity-85">
                    {diff.previous !== null && diff.previous !== undefined ? String(diff.previous) : '—'}
                  </span>
                </div>
                <div className="rounded bg-emerald-50/60 border border-emerald-200/50 p-1.5 text-emerald-900">
                  <span className="block text-[10px] uppercase font-semibold text-emerald-700">New</span>
                  <span className="break-words font-medium">
                    {diff.new !== null && diff.new !== undefined ? String(diff.new) : '—'}
                  </span>
                </div>
              </div>
            ) : (
              <ScalarValue value={diff} />
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

function MetadataValue({ value }) {
  if (Array.isArray(value)) {
    if (value.length === 0) {
      return <span className="text-muted-foreground italic text-xs">None recorded</span>
    }
    return (
      <ul className="list-disc space-y-1 pl-4 text-xs">
        {value.map((item, index) => (
          <li key={`${index}-${String(item)}`}>
            <MetadataValue value={item} />
          </li>
        ))}
      </ul>
    )
  }

  if (value && typeof value === 'object') {
    const entries = Object.entries(value)
    if (entries.length === 0) {
      return <span className="text-muted-foreground italic text-xs">No metadata</span>
    }
    return (
      <dl className="space-y-1.5 rounded bg-muted/30 p-2 text-xs">
        {entries.map(([key, item]) => (
          <div key={key} className="grid gap-1 sm:grid-cols-[8.5rem_1fr] sm:gap-2 items-baseline">
            <dt className="text-xs font-medium text-muted-foreground truncate" title={auditFieldLabel(key)}>
              {auditFieldLabel(key)}
            </dt>
            <dd className="min-w-0">
              <MetadataValue value={item} />
            </dd>
          </div>
        ))}
      </dl>
    )
  }

  return <ScalarValue value={value} />
}

function displayValue(key, value) {
  if (key === 'file_size' && Number.isInteger(value) && value >= 0) {
    return `${formatBytes(value)} (${value.toLocaleString()} bytes)`
  }
  if (Array.isArray(value)) {
    return value.map((item) => String(item)).join(', ')
  }
  if (value === null || value === undefined) {
    return 'Not recorded'
  }
  return String(value)
}

export function AuditEventDetails({ event = {}, details = event.details }) {
  const [isOpen, setIsOpen] = useState(false)
  const [copied, setCopied] = useState(false)
  const [coords, setCoords] = useState(null)
  const triggerRef = useRef(null)
  const popoverRef = useRef(null)

  const eventDetails = details && typeof details === 'object' ? details : {}
  const actorUserId =
    eventDetails.actor_user_id ?? eventDetails.actor_id ?? event.actor_id
  const metadata = {
    ...eventDetails,
    event_id: event.id,
    chain_index: event.chain_index,
    target_user_id: event.target_user_id,
    document_id: event.document_id,
    request_id: event.request_id,
    hash_schema: event.hash_schema,
    resource_type: event.resource_type,
  }
  delete metadata.actor_id
  if (actorUserId) {
    metadata.actor_user_id = actorUserId
  }
  for (const key of Object.keys(metadata)) {
    if (metadata[key] === undefined || metadata[key] === null || metadata[key] === '') {
      delete metadata[key]
    }
  }
  const entries = Object.entries(metadata)
  const summary = auditEventSummary(metadata)

  const updatePosition = useCallback(() => {
    if (!triggerRef.current) return
    const rect = triggerRef.current.getBoundingClientRect()
    const isMobile = window.innerWidth < 640
    if (isMobile) {
      setCoords({ isMobile: true })
      return
    }

    const popoverWidth = Math.min(480, window.innerWidth - 32)
    const padding = 16
    let left = rect.right - popoverWidth
    if (left < padding) left = padding
    if (left + popoverWidth > window.innerWidth - padding) {
      left = window.innerWidth - popoverWidth - padding
    }

    const panelHeight = Math.min(580, window.innerHeight - padding * 2)
    let top = rect.bottom + 6
    if (top + panelHeight > window.innerHeight - padding) {
      top = Math.max(padding, rect.top - panelHeight - 6)
    }
    top = Math.min(top, window.innerHeight - panelHeight - padding)

    setCoords({
      top: Math.max(padding, top),
      left,
      width: popoverWidth,
      isMobile: false,
    })
  }, [])

  useEffect(() => {
    if (!isOpen) return

    updatePosition()
    function handleScrollOrResize() {
      updatePosition()
    }
    function handleClickOutside(event) {
      if (
        popoverRef.current &&
        !popoverRef.current.contains(event.target) &&
        triggerRef.current &&
        !triggerRef.current.contains(event.target)
      ) {
        setIsOpen(false)
      }
    }
    function handleKeyDown(event) {
      if (event.key === 'Escape') {
        setIsOpen(false)
        triggerRef.current?.focus()
      }
    }

    window.addEventListener('resize', handleScrollOrResize)
    window.addEventListener('scroll', handleScrollOrResize, true)
    document.addEventListener('mousedown', handleClickOutside)
    document.addEventListener('keydown', handleKeyDown)

    return () => {
      window.removeEventListener('resize', handleScrollOrResize)
      window.removeEventListener('scroll', handleScrollOrResize, true)
      document.removeEventListener('mousedown', handleClickOutside)
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [isOpen, updatePosition])

  async function copyMetadata() {
    try {
      await navigator.clipboard.writeText(JSON.stringify(metadata, null, 2))
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      setCopied(false)
    }
  }

  const popoverContent = isOpen && (
    <div
      ref={popoverRef}
      role="dialog"
      aria-modal="false"
      aria-label="Event metadata details"
      style={
        coords?.isMobile
          ? {
              position: 'fixed',
              bottom: 16,
              left: 16,
              right: 16,
              maxHeight: '85vh',
              zIndex: 9999,
            }
          : coords
          ? {
              position: 'fixed',
              top: `${coords.top}px`,
              left: `${coords.left}px`,
              width: `${coords.width}px`,
              maxHeight: 'min(580px, 85vh)',
              zIndex: 9999,
            }
          : {
              position: 'fixed',
              top: '20%',
              left: '50%',
              transform: 'translateX(-50%)',
              width: 'min(480px, 90vw)',
              maxHeight: '80vh',
              zIndex: 9999,
            }
      }
      className="flex flex-col rounded-xl border border-border bg-card text-card-foreground shadow-2xl animate-in fade-in-0 zoom-in-95 overflow-hidden"
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b px-4 py-3 bg-muted/40">
        <div>
          <h4 className="text-sm font-semibold tracking-tight">Audit Event Metadata</h4>
          <p className="text-[11px] text-muted-foreground">Technical and contextual parameters</p>
        </div>
        <div className="flex items-center gap-1">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={copyMetadata}
            className="h-7 px-2 text-xs gap-1"
            aria-label="Copy event metadata"
          >
            {copied ? <Check className="size-3 text-emerald-600" /> : <Copy className="size-3" />}
            {copied ? 'Copied' : 'Copy JSON'}
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => setIsOpen(false)}
            className="h-7 w-7 p-0 text-muted-foreground hover:text-foreground"
            aria-label="Close metadata"
          >
            <X className="size-4" />
          </Button>
        </div>
      </div>

      {/* Scrollable Content Body */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {summary.length > 0 ? (
          <div className="rounded-lg bg-primary/5 border border-primary/15 p-2.5 space-y-1">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-primary">Summary</span>
            {summary.map((line) => (
              <p key={line} className="text-xs font-medium text-foreground break-words leading-relaxed">
                {line}
              </p>
            ))}
          </div>
        ) : null}

        {/* Structured Field Changes if present */}
        {metadata.field_changes ? <FieldChangesView changes={metadata.field_changes} /> : null}

        {/* Key-Value Pairs */}
        {entries.length > 0 ? (
          <dl className="divide-y divide-border/60 text-xs">
            {entries.map(([key, value]) => {
              if (key === 'field_changes') return null // Handled above cleanly
              return (
                <div key={key} className="py-2 grid grid-cols-1 sm:grid-cols-[10rem_1fr] gap-1 items-baseline">
                  <dt className="font-medium text-muted-foreground truncate" title={auditFieldLabel(key)}>
                    {auditFieldLabel(key)}
                  </dt>
                  <dd className="min-w-0">
                    {value && typeof value === 'object' ? (
                      <MetadataValue value={value} />
                    ) : (
                      <span className="break-words">
                        {key === 'file_size' ? (
                          <ScalarValue value={displayValue(key, value)} />
                        ) : (
                          <MetadataScalar field={key} value={value} />
                        )}
                      </span>
                    )}
                  </dd>
                </div>
              )
            })}
          </dl>
        ) : (
          <p className="text-xs text-muted-foreground py-4 text-center">
            No additional metadata was recorded for this event.
          </p>
        )}

        {/* Raw JSON disclosure */}
        <details className="rounded-lg border bg-muted/20 text-xs p-2.5">
          <summary className="cursor-pointer font-medium text-primary hover:underline select-none">
            Raw JSON
          </summary>
          <pre className="mt-2 max-h-52 overflow-auto rounded-md bg-muted/60 p-2.5 font-mono text-[11px] whitespace-pre-wrap break-all border">
            {JSON.stringify(metadata, null, 2)}
          </pre>
        </details>
      </div>
    </div>
  )

  return (
    <div className="relative inline-block text-left">
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setIsOpen((prev) => !prev)}
        className="inline-flex items-center gap-1 text-xs font-medium text-primary hover:text-primary/80 transition-colors py-1 px-1.5 -mx-1.5 rounded hover:bg-primary/5 focus:outline-none focus:ring-1 focus:ring-ring"
        aria-expanded={isOpen}
      >
        <span>View metadata</span>
        {isOpen ? <ChevronUp className="size-3" /> : <ChevronDown className="size-3" />}
      </button>

      {typeof document !== 'undefined' && isOpen && createPortal(popoverContent, document.body)}
    </div>
  )
}
