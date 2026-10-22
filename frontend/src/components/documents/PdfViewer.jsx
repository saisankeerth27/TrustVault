import { useEffect, useRef, useState } from 'react'
import {
  ChevronLeft,
  ChevronRight,
  Download,
  LoaderCircle,
  RefreshCw,
  ZoomIn,
  ZoomOut,
} from 'lucide-react'
import * as pdfjsLib from 'pdfjs-dist'
import pdfjsWorker from 'pdfjs-dist/build/pdf.worker.min.mjs?url'
import { Button } from '@/components/ui/button'
import { saveBlob } from '@/lib/documents'

if (typeof window !== 'undefined' && !pdfjsLib.GlobalWorkerOptions.workerSrc) {
  pdfjsLib.GlobalWorkerOptions.workerSrc = pdfjsWorker
}

export function PdfViewer({ blob, filename }) {
  const [pdfDoc, setPdfDoc] = useState(null)
  const [pageNum, setPageNum] = useState(1)
  const [numPages, setNumPages] = useState(0)
  const [scale, setScale] = useState(1.2)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState(null)
  const [renderError, setRenderError] = useState(null)
  const canvasRef = useRef(null)
  const renderTaskRef = useRef(null)

  // Load PDF Document from blob
  useEffect(() => {
    let active = true
    let loadingTask = null

    async function loadPdf() {
      setIsLoading(true)
      setError(null)
      try {
        const arrayBuffer = await blob.arrayBuffer()
        loadingTask = pdfjsLib.getDocument({
          data: arrayBuffer,
          isEvalSupported: false,
        })
        const loadedDoc = await loadingTask.promise
        if (!active) {
          return
        }
        setPdfDoc(loadedDoc)
        setNumPages(loadedDoc.numPages)
        setPageNum(1)
      } catch (err) {
        if (!active) return
        setError(err?.message || 'The PDF document could not be rendered.')
      } finally {
        if (active) {
          setIsLoading(false)
        }
      }
    }

    loadPdf()

    return () => {
      active = false
      if (loadingTask) {
        try {
          loadingTask.destroy()
        } catch {
          // ignore cleanup errors
        }
      }
    }
  }, [blob])

  // Render current page onto canvas
  useEffect(() => {
    if (!pdfDoc || !canvasRef.current) {
      return undefined
    }

    let isCurrent = true

    if (renderTaskRef.current) {
      try {
        renderTaskRef.current.cancel()
      } catch {
        // ignore cancellation errors
      }
      renderTaskRef.current = null
    }

    async function renderPage() {
      setRenderError(null)
      try {
        const page = await pdfDoc.getPage(pageNum)
        if (!isCurrent || !canvasRef.current) {
          return
        }

        const pixelRatio = window.devicePixelRatio || 1
        const viewport = page.getViewport({ scale })
        const canvas = canvasRef.current
        const context = canvas.getContext('2d')

        canvas.width = Math.floor(viewport.width * pixelRatio)
        canvas.height = Math.floor(viewport.height * pixelRatio)
        canvas.style.width = `${Math.floor(viewport.width)}px`
        canvas.style.height = `${Math.floor(viewport.height)}px`

        const transform =
          pixelRatio !== 1 ? [pixelRatio, 0, 0, pixelRatio, 0, 0] : null

        const renderTask = page.render({
          canvasContext: context,
          viewport,
          transform,
        })
        renderTaskRef.current = renderTask

        await renderTask.promise
      } catch (err) {
        if (err?.name === 'RenderingCancelledException') {
          return
        }
        if (isCurrent) {
          setRenderError(err?.message || 'Page rendering failed.')
        }
      }
    }

    renderPage()

    return () => {
      isCurrent = false
      if (renderTaskRef.current) {
        try {
          renderTaskRef.current.cancel()
        } catch {
          // ignore
        }
      }
    }
  }, [pdfDoc, pageNum, scale])

  function handlePrev() {
    setPageNum((prev) => Math.max(1, prev - 1))
  }

  function handleNext() {
    setPageNum((prev) => Math.min(numPages, prev + 1))
  }

  function handleZoomIn() {
    setScale((prev) => Math.min(2.5, +(prev + 0.2).toFixed(1)))
  }

  function handleZoomOut() {
    setScale((prev) => Math.max(0.6, +(prev - 0.2).toFixed(1)))
  }

  function handleDownload() {
    saveBlob(blob, filename || 'document.pdf')
  }

  if (isLoading) {
    return (
      <div
        className="flex min-h-72 items-center justify-center gap-3 rounded-lg border border-dashed text-sm text-muted-foreground"
        aria-busy="true"
        aria-live="polite"
      >
        <LoaderCircle className="size-5 animate-spin text-primary" aria-hidden="true" />
        Loading secure PDF viewer...
      </div>
    )
  }

  if (error) {
    return (
      <div className="space-y-4 rounded-lg border border-destructive/30 bg-destructive/5 p-6 text-sm text-destructive">
        <p className="font-medium" role="alert">
          {error}
        </p>
        <p className="text-xs text-muted-foreground">
          The PDF content was retrieved safely through the authenticated API but could not
          be parsed in-browser. Download it to view in an external PDF reader.
        </p>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={handleDownload}
        >
          <Download className="size-4" aria-hidden="true" />
          Download PDF
        </Button>
      </div>
    )
  }

  return (
    <div className="flex flex-col rounded-lg border bg-muted/10 shadow-xs">
      {/* Viewer controls bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b bg-muted/30 px-4 py-2.5 text-xs">
        <div className="flex items-center gap-1.5">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={handlePrev}
            disabled={pageNum <= 1}
            aria-label="Previous page"
            className="h-8 px-2"
          >
            <ChevronLeft className="size-4" aria-hidden="true" />
          </Button>
          <span className="font-medium text-foreground">
            Page {pageNum} of {numPages}
          </span>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={handleNext}
            disabled={pageNum >= numPages}
            aria-label="Next page"
            className="h-8 px-2"
          >
            <ChevronRight className="size-4" aria-hidden="true" />
          </Button>
        </div>

        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1 border-r pr-2">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={handleZoomOut}
              disabled={scale <= 0.6}
              aria-label="Zoom out"
              className="h-8 px-2"
            >
              <ZoomOut className="size-4" aria-hidden="true" />
            </Button>
            <span className="w-12 text-center font-mono text-[11px] text-muted-foreground">
              {Math.round(scale * 100)}%
            </span>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={handleZoomIn}
              disabled={scale >= 2.5}
              aria-label="Zoom in"
              className="h-8 px-2"
            >
              <ZoomIn className="size-4" aria-hidden="true" />
            </Button>
          </div>

          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={handleDownload}
            aria-label="Download document PDF"
            className="h-8 gap-1.5 px-3"
          >
            <Download className="size-3.5" aria-hidden="true" />
            Download
          </Button>
        </div>
      </div>

      {/* Canvas container */}
      <div className="flex min-h-[30rem] max-h-[40rem] justify-center overflow-auto p-4 bg-muted/30">
        {renderError ? (
          <div className="flex flex-col items-center justify-center gap-2 text-destructive">
            <p className="text-sm font-medium">{renderError}</p>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setPageNum((p) => p)}
            >
              <RefreshCw className="size-3.5" aria-hidden="true" />
              Retry page
            </Button>
          </div>
        ) : (
          <canvas
            ref={canvasRef}
            className="rounded-sm bg-white shadow-md transition-shadow"
            role="img"
            aria-label={`PDF page ${pageNum} of ${numPages}`}
          />
        )}
      </div>
    </div>
  )
}
