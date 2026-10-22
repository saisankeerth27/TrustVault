import { useState } from 'react'
import { Check, Copy } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  auditEventSummary,
  auditFieldLabel,
} from '@/lib/audit'
import { formatBytes } from '@/lib/documents'

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
const HEX_PATTERN = /^[0-9a-f]{64}$/i
const ISO_DATE_PATTERN = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/

function ScalarValue({ value }) {
  if (typeof value === 'boolean') {
    return <span>{value ? 'Yes' : 'No'}</span>
  }
  if (value === null || value === undefined) {
    return <span className="text-muted-foreground">Not recorded</span>
  }

  const text = String(value)
  const monospaced =
    UUID_PATTERN.test(text) || HEX_PATTERN.test(text) || ISO_DATE_PATTERN.test(text)

  return (
    <span
      className={
        monospaced
          ? 'font-mono text-xs break-all whitespace-pre-wrap'
          : 'break-words whitespace-pre-wrap'
      }
    >
      {text}
    </span>
  )
}

function MetadataValue({ value }) {
  if (Array.isArray(value)) {
    if (value.length === 0) {
      return <span className="text-muted-foreground">None recorded</span>
    }
    return (
      <ul className="list-disc space-y-1 pl-5">
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
      return <span className="text-muted-foreground">No metadata</span>
    }
    return (
      <dl className="space-y-1.5">
        {entries.map(([key, item]) => (
          <div key={key} className="grid gap-1 sm:grid-cols-[10rem_1fr] sm:gap-3">
            <dt className="text-xs font-medium text-muted-foreground">
              {auditFieldLabel(key)}
            </dt>
            <dd>
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

export function AuditEventDetails({ details }) {
  const [copied, setCopied] = useState(false)
  const metadata = details && typeof details === 'object' ? details : {}
  const entries = Object.entries(metadata)
  const summary = auditEventSummary(metadata)

  async function copyMetadata() {
    try {
      await navigator.clipboard.writeText(JSON.stringify(metadata, null, 2))
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1_500)
    } catch {
      setCopied(false)
    }
  }

  return (
    <details className="group max-w-sm">
      <summary className="cursor-pointer text-xs font-medium text-primary">
        View metadata
      </summary>
      <div className="mt-3 space-y-4 rounded-lg border bg-muted/20 p-3">
        {summary.length > 0 ? (
          <div className="space-y-1 text-xs">
            {summary.map((line) => (
              <p key={line} className="break-words">
                {line}
              </p>
            ))}
          </div>
        ) : null}

        {entries.length > 0 ? (
          <dl className="space-y-2 text-xs">
            {entries.map(([key, value]) => (
              <div key={key} className="grid gap-1">
                <dt className="font-medium text-muted-foreground">
                  {auditFieldLabel(key)}
                </dt>
                <dd className="min-w-0">
                  {value && typeof value === 'object' ? (
                    <MetadataValue value={value} />
                  ) : (
                    <span className="break-words whitespace-pre-wrap">
                      {displayValue(key, value)}
                    </span>
                  )}
                </dd>
              </div>
            ))}
          </dl>
        ) : (
          <p className="text-xs text-muted-foreground">
            No additional metadata was recorded.
          </p>
        )}

        <div className="flex flex-wrap items-center gap-2 border-t pt-3">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={copyMetadata}
            aria-label="Copy event metadata"
          >
            {copied ? (
              <Check className="size-3.5" aria-hidden="true" />
            ) : (
              <Copy className="size-3.5" aria-hidden="true" />
            )}
            {copied ? 'Copied' : 'Copy JSON'}
          </Button>
          <details className="min-w-0 flex-1">
            <summary className="cursor-pointer text-xs font-medium text-primary">
              Raw JSON
            </summary>
            <pre className="mt-2 max-h-64 overflow-auto rounded-md bg-muted/60 p-3 text-xs whitespace-pre-wrap break-all">
              {JSON.stringify(metadata, null, 2)}
            </pre>
          </details>
        </div>
      </div>
    </details>
  )
}
