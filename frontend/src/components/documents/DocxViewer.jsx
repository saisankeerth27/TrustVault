import { useCallback, useEffect, useRef, useState } from 'react'
import { ChevronLeft, ChevronRight, FileWarning, LoaderCircle, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'

/**
 * Paginated DOCX preview.
 *
 * docx-preview renders the document into distinct <section> elements. It can
 * break pages on manual page breaks, Word's <w:lastRenderedPageBreak> markers,
 * and section changes. It does not reflow text in real time, so a DOCX saved
 * without page-break hints may render as a single long page.
 */
export function DocxViewer({ blob, filename }) {
  const [pageCount, setPageCount] = useState(0)
  const [currentPage, setCurrentPage] = useState(1)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState(null)
  const [retryKey, setRetryKey] = useState(0)
  const containerRef = useRef(null)
  const scrollRef = useRef(null)
  const pageRefs = useRef([])

  useEffect(() => {
    let active = true
    const container = containerRef.current

    if (!container || !blob) {
      return undefined
    }

    setIsLoading(true)
    setError(null)
    setPageCount(0)
    setCurrentPage(1)
    pageRefs.current = []
    container.innerHTML = ''

    import('docx-preview')
      .then(({ renderAsync }) =>
        renderAsync(blob, container, undefined, {
          className: 'docx',
          inWrapper: true,
          breakPages: true,
          // Word writes <w:lastRenderedPageBreak> markers. Honouring them
          // gives realistic page boundaries without reflowing the document.
          ignoreLastRenderedPageBreak: false,
          ignoreWidth: false,
          ignoreHeight: false,
          renderHeaders: true,
          renderFooters: true,
          renderFootnotes: true,
          renderEndnotes: true,
          experimental: true,
        }),
      )
      .then(() => {
        if (!active) {
          return
        }
        const pages = Array.from(container.querySelectorAll('section.docx'))
        pageRefs.current = pages
        setPageCount(pages.length)
        setCurrentPage(1)
        setIsLoading(false)
      })
      .catch((renderError) => {
        if (!active) {
          return
        }
        setError(renderError)
        setIsLoading(false)
      })

    return () => {
      active = false
    }
  }, [blob, retryKey])

  const goToPage = useCallback(
    (requestedPage) => {
      const bounded = Math.min(Math.max(1, requestedPage), pageCount || 1)
      setCurrentPage(bounded)
      const target = pageRefs.current[bounded - 1]
      const scroller = scrollRef.current
      if (target && scroller && typeof scroller.scrollTo === 'function') {
        scroller.scrollTo({ top: Math.max(0, target.offsetTop - 8), behavior: 'smooth' })
      }
    },
    [pageCount],
  )

  function handleScroll() {
    const scroller = scrollRef.current
    const pages = pageRefs.current
    if (!scroller || pages.length === 0) {
      return
    }
    const position = scroller.scrollTop + 16
    let nextPage = 1
    pages.forEach((page, index) => {
      if (page.offsetTop <= position) {
        nextPage = index + 1
      }
    })
    setCurrentPage(nextPage)
  }

  if (error) {
    return (
      <div className="space-y-4 rounded-lg border border-destructive/30 bg-destructive/5 p-6 text-sm text-destructive">
        <div className="flex items-start gap-3">
          <FileWarning className="mt-0.5 size-5 shrink-0" aria-hidden="true" />
          <div>
            <p className="font-medium" role="alert">
              This DOCX file could not be rendered in the browser.
            </p>
            <p className="mt-1 text-xs text-muted-foreground">
              The file was retrieved safely through the authenticated API, but its Word
              layout is unsupported or damaged. Download it to open it in Word.
            </p>
          </div>
        </div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => {
            // Clear the error first so the render container is mounted again
            // before the retry effect runs.
            setError(null)
            setIsLoading(true)
            setRetryKey((key) => key + 1)
          }}
        >
          <RefreshCw className="size-4" aria-hidden="true" />
          Retry preview
        </Button>
      </div>
    )
  }

  return (
    <div className="flex flex-col rounded-lg border bg-muted/10 shadow-xs">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b bg-muted/30 px-4 py-2.5 text-xs">
        <div className="flex items-center gap-1.5">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => goToPage(currentPage - 1)}
            disabled={isLoading || currentPage <= 1}
            aria-label="Previous page"
            className="h-8 px-2"
          >
            <ChevronLeft className="size-4" aria-hidden="true" />
          </Button>
          <span className="font-medium text-foreground" aria-live="polite">
            {isLoading
              ? 'Rendering document...'
              : `Page ${currentPage} of ${Math.max(pageCount, 1)}`}
          </span>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => goToPage(currentPage + 1)}
            disabled={isLoading || pageCount === 0 || currentPage >= pageCount}
            aria-label="Next page"
            className="h-8 px-2"
          >
            <ChevronRight className="size-4" aria-hidden="true" />
          </Button>
        </div>
        <span className="max-w-[16rem] truncate font-mono text-[11px] text-muted-foreground">
          {filename}
        </span>
      </div>

      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="relative max-h-[40rem] min-h-[30rem] overflow-auto bg-muted/30 p-4"
      >
        {isLoading ? (
          <div
            className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center gap-3 bg-muted/30 text-sm text-muted-foreground"
            aria-busy="true"
            aria-live="polite"
          >
            <LoaderCircle className="size-5 animate-spin text-primary" aria-hidden="true" />
            Loading secure DOCX preview...
          </div>
        ) : null}
        <div
          ref={containerRef}
          className="docx-preview-root mx-auto flex w-fit min-w-full flex-col items-center"
        />
      </div>

      {!isLoading && pageCount <= 1 ? (
        <p className="border-t px-4 py-2 text-[11px] text-muted-foreground">
          This document has no page-break markers, so it is shown as one continuous
          page. Word documents saved with page breaks or section changes show separate
          pages here.
        </p>
      ) : null}
    </div>
  )
}
