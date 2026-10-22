/**
 * PdfAnnotationEditor — Browser-based PDF annotation editor
 *
 * Uses pdfjs-dist for rendering and pdf-lib for embedding annotations into the PDF binary.
 *
 * SUPPORTED EDITING CAPABILITIES (accurately described):
 *  - Text note: sticky-note style annotation placed at any click position on any page
 *  - Free text (typewriter): types visible text directly onto the PDF canvas
 *  - Highlight rectangle: click-drag to draw a translucent yellow highlight box
 *  - Signature/initials: typed signature in italic style placed at click position
 *
 * NOT SUPPORTED (requires commercial SDK):
 *  - Editing or removing existing body text in the PDF
 *  - OCR-based text selection for highlights
 *  - Form field filling (AcroForm / XFA)
 *
 * Workflow:
 *   1. PDF rendered in <canvas> via pdfjs-dist
 *   2. User places annotations by clicking/dragging on canvas
 *   3. On save: pdf-lib loads the original bytes, embeds annotations as drawn graphics
 *   4. Annotated PDF uploaded as new revision via PUT /api/v1/documents/{id}/versions
 *   5. Optimistic concurrency control via expected_version_number
 */
import { useEffect, useRef, useState } from 'react'
import {
  ChevronLeft,
  ChevronRight,
  Edit3,
  Highlighter,
  LoaderCircle,
  MessageSquare,
  Pen,
  Save,
  ShieldCheck,
  Type,
  X,
  ZoomIn,
  ZoomOut,
} from 'lucide-react'
import * as pdfjsLib from 'pdfjs-dist'
import pdfjsWorker from 'pdfjs-dist/build/pdf.worker.min.mjs?url'
import { PDFDocument, rgb, StandardFonts } from 'pdf-lib'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { getApiErrorMessage } from '@/services/api'
import { createDocumentVersion } from '@/services/documents'

if (typeof window !== 'undefined' && !pdfjsLib.GlobalWorkerOptions.workerSrc) {
  pdfjsLib.GlobalWorkerOptions.workerSrc = pdfjsWorker
}

const TOOL_TYPES = {
  TEXT_NOTE: 'text_note',
  FREE_TEXT: 'free_text',
  HIGHLIGHT: 'highlight',
  SIGNATURE: 'signature',
}

const TOOL_META = {
  [TOOL_TYPES.TEXT_NOTE]: {
    label: 'Text note',
    description: 'Click to add a sticky-note annotation',
    Icon: MessageSquare,
  },
  [TOOL_TYPES.FREE_TEXT]: {
    label: 'Free text',
    description: 'Click to type text directly on the page (typewriter)',
    Icon: Type,
  },
  [TOOL_TYPES.HIGHLIGHT]: {
    label: 'Highlight',
    description: 'Click and drag to highlight an area',
    Icon: Highlighter,
  },
  [TOOL_TYPES.SIGNATURE]: {
    label: 'Signature',
    description: 'Click to add typed signature or initials',
    Icon: Pen,
  },
}

function AnnotationInputDialog({ tool, onConfirm, onCancel }) {
  const [text, setText] = useState('')
  const inputRef = useRef(null)

  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  const meta = TOOL_META[tool] || {}

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      if (text.trim()) onConfirm(text.trim())
    }
    if (e.key === 'Escape') onCancel()
  }

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 9999,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'rgba(0,0,0,0.4)',
      }}
      role="dialog"
      aria-modal="true"
      aria-label={`Add ${meta.label} annotation`}
    >
      <div
        style={{ width: 'min(400px, 90vw)' }}
        className="rounded-xl border bg-card p-5 shadow-2xl space-y-3"
      >
        <p className="text-sm font-semibold text-foreground">
          {meta.label}
        </p>
        <p className="text-xs text-muted-foreground">{meta.description}</p>
        <textarea
          ref={inputRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={
            tool === TOOL_TYPES.SIGNATURE
              ? 'Type your name or initials'
              : 'Type annotation text'
          }
          rows={tool === TOOL_TYPES.SIGNATURE ? 1 : 3}
          maxLength={500}
          className="flex min-h-[60px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          aria-label="Annotation text"
          style={tool === TOOL_TYPES.SIGNATURE ? { fontStyle: 'italic', fontSize: 16 } : {}}
        />
        <p className="text-xs text-muted-foreground">Enter to confirm · Escape to cancel</p>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" size="sm" onClick={onCancel}>Cancel</Button>
          <Button
            type="button"
            size="sm"
            disabled={!text.trim()}
            onClick={() => text.trim() && onConfirm(text.trim())}
          >
            Add
          </Button>
        </div>
      </div>
    </div>
  )
}

export function PdfAnnotationEditor({
  blob,
  filename,
  documentRecord,
  currentVersion,
  onSaved,
  onConflict,
  onCancel,
}) {
  const [pdfDoc, setPdfDoc] = useState(null)
  const [pageNum, setPageNum] = useState(1)
  const [numPages, setNumPages] = useState(0)
  const [scale, setScale] = useState(1.2)
  const [isLoadingPdf, setIsLoadingPdf] = useState(true)
  const [pdfError, setPdfError] = useState(null)

  const [annotations, setAnnotations] = useState([])
  const [activeTool, setActiveTool] = useState(TOOL_TYPES.TEXT_NOTE)
  const [pendingClick, setPendingClick] = useState(null)

  // Highlight drag state
  const [highlightStart, setHighlightStart] = useState(null)
  const [highlightPreview, setHighlightPreview] = useState(null)

  const [isSaving, setIsSaving] = useState(false)
  const [saveError, setSaveError] = useState(null)
  const [saveProgress, setSaveProgress] = useState(0)
  const [changeSummary, setChangeSummary] = useState('')

  const canvasRef = useRef(null)
  const renderTaskRef = useRef(null)
  const loadingTaskRef = useRef(null)

  // Load PDF
  useEffect(() => {
    let active = true
    async function load() {
      setIsLoadingPdf(true)
      setPdfError(null)
      try {
        const buf = await blob.arrayBuffer()
        const task = pdfjsLib.getDocument({ data: buf, isEvalSupported: false })
        loadingTaskRef.current = task
        const doc = await task.promise
        if (!active) return
        setPdfDoc(doc)
        setNumPages(doc.numPages)
        setPageNum(1)
      } catch (err) {
        if (active) setPdfError(err?.message || 'Could not load PDF.')
      } finally {
        if (active) setIsLoadingPdf(false)
      }
    }
    load()
    return () => {
      active = false
      try { loadingTaskRef.current?.destroy() } catch { /* noop */ }
    }
  }, [blob])

  // Render page
  useEffect(() => {
    if (!pdfDoc || !canvasRef.current) return undefined
    let active = true
    try { renderTaskRef.current?.cancel() } catch { /* noop */ }
    renderTaskRef.current = null

    async function render() {
      try {
        const page = await pdfDoc.getPage(pageNum)
        if (!active || !canvasRef.current) return
        const pr = window.devicePixelRatio || 1
        const vp = page.getViewport({ scale })
        const canvas = canvasRef.current
        canvas.width = Math.floor(vp.width * pr)
        canvas.height = Math.floor(vp.height * pr)
        canvas.style.width = `${Math.floor(vp.width)}px`
        canvas.style.height = `${Math.floor(vp.height)}px`
        const task = page.render({
          canvasContext: canvas.getContext('2d'),
          viewport: vp,
          transform: pr !== 1 ? [pr, 0, 0, pr, 0, 0] : null,
        })
        renderTaskRef.current = task
        await task.promise
      } catch (err) {
        if (err?.name !== 'RenderingCancelledException') {
          console.warn('render error', err)
        }
      }
    }
    render()
    return () => {
      active = false
      try { renderTaskRef.current?.cancel() } catch { /* noop */ }
    }
  }, [pdfDoc, pageNum, scale])

  function getCanvasRelativeCoords(e) {
    if (!canvasRef.current) return { x: 0, y: 0 }
    const r = canvasRef.current.getBoundingClientRect()
    return { x: (e.clientX - r.left) / scale, y: (e.clientY - r.top) / scale }
  }

  function handleMouseDown(e) {
    if (e.button !== 0 || isSaving) return
    if (activeTool === TOOL_TYPES.HIGHLIGHT) {
      const c = getCanvasRelativeCoords(e)
      setHighlightStart(c)
      setHighlightPreview(null)
      return
    }
    const c = getCanvasRelativeCoords(e)
    setPendingClick({ x: c.x, y: c.y, pageIndex: pageNum - 1 })
  }

  function handleMouseMove(e) {
    if (activeTool !== TOOL_TYPES.HIGHLIGHT || !highlightStart || isSaving) return
    const c = getCanvasRelativeCoords(e)
    setHighlightPreview({
      x: Math.min(highlightStart.x, c.x),
      y: Math.min(highlightStart.y, c.y),
      w: Math.abs(c.x - highlightStart.x),
      h: Math.abs(c.y - highlightStart.y),
    })
  }

  function handleMouseUp(e) {
    if (activeTool !== TOOL_TYPES.HIGHLIGHT || !highlightStart || isSaving) return
    const c = getCanvasRelativeCoords(e)
    const rect = {
      x: Math.min(highlightStart.x, c.x),
      y: Math.min(highlightStart.y, c.y),
      w: Math.abs(c.x - highlightStart.x),
      h: Math.abs(c.y - highlightStart.y),
    }
    setHighlightStart(null)
    setHighlightPreview(null)
    if (rect.w > 5 && rect.h > 5) {
      setAnnotations((prev) => [
        ...prev,
        {
          id: `ann-${Date.now()}`,
          type: TOOL_TYPES.HIGHLIGHT,
          pageIndex: pageNum - 1,
          x: rect.x,
          y: rect.y,
          w: rect.w,
          h: rect.h,
          text: 'Highlight',
        },
      ])
    }
  }

  function handleAnnotationConfirm(text) {
    if (!pendingClick) return
    setAnnotations((prev) => [
      ...prev,
      {
        id: `ann-${Date.now()}`,
        type: activeTool,
        pageIndex: pendingClick.pageIndex,
        x: pendingClick.x,
        y: pendingClick.y,
        text,
      },
    ])
    setPendingClick(null)
  }

  function removeAnnotation(id) {
    setAnnotations((prev) => prev.filter((a) => a.id !== id))
  }

  const currentPageAnnotations = annotations.filter((a) => a.pageIndex === pageNum - 1)
  const hasAnnotations = annotations.length > 0

  async function handleSave(e) {
    e.preventDefault()
    if (!hasAnnotations || !currentVersion || isSaving) return
    setSaveError(null)
    setIsSaving(true)
    setSaveProgress(5)

    try {
      const originalBytes = await blob.arrayBuffer()
      setSaveProgress(15)
      const pdfLibDoc = await PDFDocument.load(originalBytes, { ignoreEncryption: true })
      setSaveProgress(25)
      const helvetica = await pdfLibDoc.embedFont(StandardFonts.Helvetica)
      const pages = pdfLibDoc.getPages()
      setSaveProgress(35)

      for (const ann of annotations) {
        const page = pages[ann.pageIndex]
        if (!page) continue
        const { height: pH } = page.getSize()
        // Convert top-left → bottom-left (PDF coordinate system)
        const pdfY = pH - ann.y

        switch (ann.type) {
          case TOOL_TYPES.TEXT_NOTE:
            page.drawRectangle({
              x: ann.x, y: pdfY - 22, width: 160, height: 22,
              color: rgb(1, 0.95, 0.7), borderColor: rgb(0.95, 0.65, 0.1), borderWidth: 1,
              opacity: 0.9,
            })
            page.drawText(ann.text, {
              x: ann.x + 4, y: pdfY - 16, font: helvetica, size: 9,
              color: rgb(0.1, 0.1, 0.1), maxWidth: 152,
            })
            break
          case TOOL_TYPES.FREE_TEXT:
            page.drawText(ann.text, {
              x: ann.x, y: pdfY - 13, font: helvetica, size: 12,
              color: rgb(0.05, 0.27, 0.71),
            })
            break
          case TOOL_TYPES.HIGHLIGHT:
            page.drawRectangle({
              x: ann.x, y: pH - ann.y - (ann.h || 20),
              width: ann.w || 100, height: ann.h || 20,
              color: rgb(0.99, 0.87, 0.1), opacity: 0.35,
            })
            break
          case TOOL_TYPES.SIGNATURE:
            page.drawText(ann.text, {
              x: ann.x, y: pdfY - 18, font: helvetica, size: 18,
              color: rgb(0.05, 0.25, 0.67),
            })
            page.drawLine({
              start: { x: ann.x, y: pdfY - 20 },
              end: { x: ann.x + Math.min(ann.text.length * 10, 200), y: pdfY - 20 },
              thickness: 1, color: rgb(0.05, 0.25, 0.67),
            })
            break
          default:
            break
        }
      }

      setSaveProgress(60)
      const annotatedBytes = await pdfLibDoc.save()
      setSaveProgress(70)

      const file = new File(
        [new Blob([annotatedBytes], { type: 'application/pdf' })],
        filename || documentRecord?.name || 'annotated.pdf',
        { type: 'application/pdf' },
      )

      const summaryText =
        changeSummary.trim() ||
        `Added ${annotations.length} annotation(s) in browser`

      const result = await createDocumentVersion(
        documentRecord.id,
        file,
        currentVersion.version_number,
        summaryText,
        (p) => setSaveProgress(70 + Math.round(p * 0.3)),
      )

      setSaveProgress(100)
      onSaved(result)
    } catch (err) {
      if (err?.response?.status === 409) {
        onConflict?.()
        setSaveError(
          `${getApiErrorMessage(err)} Reload to get the latest version, then re-apply your annotations.`,
        )
      } else {
        setSaveError(getApiErrorMessage(err))
      }
    } finally {
      setIsSaving(false)
    }
  }

  if (isLoadingPdf) {
    return (
      <Card>
        <CardContent className="flex min-h-64 items-center justify-center gap-3 text-sm text-muted-foreground">
          <LoaderCircle className="size-5 animate-spin" aria-hidden="true" />
          Loading PDF editor…
        </CardContent>
      </Card>
    )
  }

  if (pdfError) {
    return (
      <Card>
        <CardContent className="space-y-3 p-6 text-sm">
          <p role="alert" className="font-medium text-destructive">{pdfError}</p>
          <p className="text-muted-foreground">The PDF could not be opened for editing.</p>
          <Button type="button" variant="outline" size="sm" onClick={onCancel}>
            <X className="size-4" aria-hidden="true" />
            Close editor
          </Button>
        </CardContent>
      </Card>
    )
  }

  return (
    <>
      {pendingClick && activeTool !== TOOL_TYPES.HIGHLIGHT ? (
        <AnnotationInputDialog
          tool={activeTool}
          onConfirm={handleAnnotationConfirm}
          onCancel={() => setPendingClick(null)}
        />
      ) : null}

      <Card className="border-primary/20">
        <CardHeader className="flex-row items-start justify-between gap-4">
          <div className="space-y-1.5">
            <CardTitle className="flex items-center gap-2">
              <Edit3 className="size-4 text-primary" aria-hidden="true" />
              Edit PDF — Annotations
            </CardTitle>
            <p className="text-sm text-muted-foreground">
              Add text notes, free-text, highlights, and typed signatures. Saving creates version{' '}
              {(currentVersion?.version_number ?? 0) + 1}.
            </p>
            <p className="rounded border border-amber-200 bg-amber-50 px-2.5 py-1 text-xs text-amber-800">
              This editor adds visual annotations to the PDF pages. It does not modify underlying body text.
            </p>
          </div>
          <Button type="button" variant="ghost" size="sm" onClick={onCancel} disabled={isSaving}>
            <X className="size-4" aria-hidden="true" />
            Close
          </Button>
        </CardHeader>

        <CardContent className="space-y-4">
          {saveError ? (
            <div role="alert" className="rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
              {saveError}
            </div>
          ) : null}

          {/* Tool selector + navigation */}
          <div className="flex flex-wrap items-center gap-2 rounded-lg border bg-muted/30 p-2">
            <span className="text-xs font-medium text-muted-foreground">Tool:</span>
            {Object.entries(TOOL_META).map(([type, meta]) => {
              const Icon = meta.Icon
              return (
                <Button
                  key={type}
                  type="button"
                  variant={activeTool === type ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => {
                    setActiveTool(type)
                    setHighlightStart(null)
                    setHighlightPreview(null)
                  }}
                  className="h-8 gap-1.5 px-2.5"
                  title={meta.description}
                  aria-pressed={activeTool === type}
                  disabled={isSaving}
                >
                  <Icon className="size-3.5" aria-hidden="true" />
                  <span className="hidden sm:inline">{meta.label}</span>
                </Button>
              )
            })}

            <div className="ml-auto flex items-center gap-1 border-l pl-2">
              <Button
                type="button" variant="ghost" size="sm"
                onClick={() => setPageNum((p) => Math.max(1, p - 1))}
                disabled={pageNum <= 1 || isSaving}
                aria-label="Previous page"
                className="h-8 px-2"
              >
                <ChevronLeft className="size-4" />
              </Button>
              <span className="whitespace-nowrap text-xs font-medium">{pageNum}/{numPages}</span>
              <Button
                type="button" variant="ghost" size="sm"
                onClick={() => setPageNum((p) => Math.min(numPages, p + 1))}
                disabled={pageNum >= numPages || isSaving}
                aria-label="Next page"
                className="h-8 px-2"
              >
                <ChevronRight className="size-4" />
              </Button>
              <Button
                type="button" variant="ghost" size="sm"
                onClick={() => setScale((s) => Math.max(0.6, +(s - 0.2).toFixed(1)))}
                disabled={scale <= 0.6 || isSaving}
                aria-label="Zoom out"
                className="h-8 px-2"
              >
                <ZoomOut className="size-4" />
              </Button>
              <span className="w-10 text-center text-[11px] font-mono text-muted-foreground">
                {Math.round(scale * 100)}%
              </span>
              <Button
                type="button" variant="ghost" size="sm"
                onClick={() => setScale((s) => Math.min(2.5, +(s + 0.2).toFixed(1)))}
                disabled={scale >= 2.5 || isSaving}
                aria-label="Zoom in"
                className="h-8 px-2"
              >
                <ZoomIn className="size-4" />
              </Button>
            </div>
          </div>

          <p className="text-xs text-muted-foreground">
            {activeTool === TOOL_TYPES.HIGHLIGHT
              ? 'Click and drag on the document to place a highlight rectangle.'
              : 'Click anywhere on the document to place an annotation at that position.'}
          </p>

          {/* Canvas area */}
          <div
            className="overflow-auto rounded-lg border bg-muted/20 p-2"
            style={{ maxHeight: '40rem', userSelect: 'none' }}
          >
            <div className="relative inline-block">
              <canvas
                ref={canvasRef}
                className="block rounded bg-white shadow"
                role="img"
                aria-label={`PDF page ${pageNum} of ${numPages} — click to annotate`}
                style={{
                  cursor: isSaving
                    ? 'not-allowed'
                    : activeTool === TOOL_TYPES.HIGHLIGHT
                    ? 'crosshair'
                    : 'text',
                }}
                onMouseDown={handleMouseDown}
                onMouseMove={handleMouseMove}
                onMouseUp={handleMouseUp}
              />

              {/* Highlight drag preview */}
              {highlightPreview ? (
                <div
                  style={{
                    position: 'absolute',
                    pointerEvents: 'none',
                    left: highlightPreview.x * scale,
                    top: highlightPreview.y * scale,
                    width: highlightPreview.w * scale,
                    height: highlightPreview.h * scale,
                    backgroundColor: 'rgba(251,191,36,0.3)',
                    border: '1.5px dashed #f59e0b',
                  }}
                />
              ) : null}

              {/* Annotation overlays for current page */}
              {currentPageAnnotations.map((ann) => {
                const meta = TOOL_META[ann.type] || {}
                if (ann.type === TOOL_TYPES.HIGHLIGHT) {
                  return (
                    <div
                      key={ann.id}
                      style={{
                        position: 'absolute',
                        left: ann.x * scale,
                        top: ann.y * scale,
                        width: (ann.w || 100) * scale,
                        height: (ann.h || 20) * scale,
                        backgroundColor: 'rgba(251,191,36,0.35)',
                        border: '1px dashed #f59e0b',
                        pointerEvents: 'auto',
                      }}
                    >
                      <button
                        type="button"
                        onClick={() => removeAnnotation(ann.id)}
                        style={{
                          position: 'absolute', top: -8, right: -8,
                          background: '#ef4444', border: 'none', borderRadius: '50%',
                          width: 16, height: 16, color: '#fff', fontSize: 10,
                          cursor: 'pointer', display: 'flex', alignItems: 'center',
                          justifyContent: 'center', padding: 0,
                        }}
                        aria-label="Remove highlight"
                      >
                        ×
                      </button>
                    </div>
                  )
                }
                return (
                  <div
                    key={ann.id}
                    style={{
                      position: 'absolute',
                      left: ann.x * scale,
                      top: ann.y * scale,
                      maxWidth: 200,
                      background: ann.type === TOOL_TYPES.SIGNATURE ? 'transparent' : 'rgba(255,253,230,0.95)',
                      border: ann.type === TOOL_TYPES.SIGNATURE ? 'none' : '1.5px solid #f59e0b',
                      borderRadius: 4,
                      padding: ann.type === TOOL_TYPES.SIGNATURE ? 0 : '2px 6px',
                      fontSize: ann.type === TOOL_TYPES.SIGNATURE ? 18 : 11,
                      color: ann.type === TOOL_TYPES.SIGNATURE ? '#1d4ed8' : '#1a1a1a',
                      fontStyle: ann.type === TOOL_TYPES.SIGNATURE ? 'italic' : 'normal',
                      fontWeight: ann.type === TOOL_TYPES.SIGNATURE ? 'bold' : 'normal',
                      fontFamily: ann.type === TOOL_TYPES.SIGNATURE ? 'Georgia, serif' : 'inherit',
                      boxShadow: ann.type !== TOOL_TYPES.SIGNATURE ? '0 1px 4px rgba(0,0,0,0.12)' : 'none',
                      pointerEvents: 'auto',
                      whiteSpace: 'pre-wrap',
                      wordBreak: 'break-word',
                    }}
                  >
                    {ann.text}
                    <button
                      type="button"
                      onClick={() => removeAnnotation(ann.id)}
                      style={{
                        position: 'absolute', top: -8, right: -8,
                        background: '#ef4444', border: 'none', borderRadius: '50%',
                        width: 16, height: 16, color: '#fff', fontSize: 10,
                        cursor: 'pointer', display: 'flex', alignItems: 'center',
                        justifyContent: 'center', padding: 0,
                      }}
                      aria-label={`Remove ${meta.label || 'annotation'}`}
                    >
                      ×
                    </button>
                  </div>
                )
              })}
            </div>
          </div>

          {/* Annotation summary */}
          {annotations.length > 0 ? (
            <div className="rounded-lg border bg-muted/20 p-3 text-xs space-y-1.5">
              <p className="font-semibold text-foreground">
                {annotations.length} annotation{annotations.length !== 1 ? 's' : ''} across {new Set(annotations.map((a) => a.pageIndex)).size} page{new Set(annotations.map((a) => a.pageIndex)).size !== 1 ? 's' : ''}
              </p>
              {annotations.map((ann) => (
                <div key={ann.id} className="flex items-center justify-between gap-2">
                  <span className="truncate text-muted-foreground">
                    <span className="font-medium text-foreground capitalize">
                      {TOOL_META[ann.type]?.label}
                    </span>{' '}
                    — p.{ann.pageIndex + 1}: {ann.text.slice(0, 60)}{ann.text.length > 60 ? '…' : ''}
                  </span>
                  <button
                    type="button"
                    className="shrink-0 text-xs text-destructive hover:underline"
                    onClick={() => removeAnnotation(ann.id)}
                    disabled={isSaving}
                  >
                    Remove
                  </button>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-muted-foreground">No annotations added yet.</p>
          )}

          {/* Save form */}
          <form className="space-y-3" onSubmit={handleSave}>
            <div className="space-y-1.5">
              <label htmlFor="pdf-ann-summary" className="text-sm font-medium">
                Change summary{' '}
                <span className="font-normal text-muted-foreground">(optional)</span>
              </label>
              <input
                id="pdf-ann-summary"
                type="text"
                maxLength={500}
                value={changeSummary}
                onChange={(e) => setChangeSummary(e.target.value)}
                placeholder={`Added ${annotations.length || 0} annotation(s) in browser`}
                disabled={isSaving}
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-xs placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
              />
            </div>

            {isSaving ? (
              <div className="space-y-2" aria-live="polite">
                <div className="flex justify-between text-xs text-muted-foreground">
                  <span>Embedding annotations and uploading…</span>
                  <span>{saveProgress}%</span>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-muted">
                  <div
                    className="h-full rounded-full bg-primary transition-all"
                    style={{ width: `${saveProgress}%` }}
                  />
                </div>
              </div>
            ) : null}

            <div className="flex flex-wrap items-center gap-3">
              <Button
                type="submit"
                disabled={!hasAnnotations || !currentVersion || isSaving}
              >
                {isSaving ? (
                  <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
                ) : (
                  <Save className="size-4" aria-hidden="true" />
                )}
                {isSaving ? 'Saving annotated PDF…' : 'Save annotated PDF as new version'}
              </Button>
              <Button type="button" variant="outline" onClick={onCancel} disabled={isSaving}>
                Cancel
              </Button>
              <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <ShieldCheck className="size-3.5" aria-hidden="true" />
                Annotations are embedded before upload. The server validates and audits every version.
              </span>
            </div>
          </form>
        </CardContent>
      </Card>
    </>
  )
}
