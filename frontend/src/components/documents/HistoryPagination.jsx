import { ChevronLeft, ChevronRight } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

function visiblePages(page, pages) {
  if (pages <= 5) {
    return Array.from({ length: pages }, (_, index) => index + 1)
  }

  const start = Math.max(1, Math.min(page - 2, pages - 4))
  return Array.from({ length: 5 }, (_, index) => start + index)
}

export function HistoryPagination({
  page,
  pages,
  pageSize,
  total,
  onPageChange,
  itemLabel = 'items',
  className,
}) {
  if (pages <= 0) {
    return null
  }

  const firstItem = total === 0 ? 0 : (page - 1) * pageSize + 1
  const lastItem = Math.min(page * pageSize, total)
  const pageNumbers = visiblePages(page, pages)

  return (
    <nav
      aria-label={`${itemLabel} pagination`}
      className={cn(
        'flex flex-col gap-3 border-t pt-4 sm:flex-row sm:items-center sm:justify-between',
        className,
      )}
    >
      <p className="text-xs text-muted-foreground">
        Showing {firstItem}-{lastItem} of {total} {itemLabel}
      </p>
      <div className="flex flex-wrap items-center gap-1">
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => onPageChange(page - 1)}
          disabled={page <= 1}
          aria-label={`Previous ${itemLabel} page`}
        >
          <ChevronLeft className="size-4" aria-hidden="true" />
          Previous
        </Button>
        {pageNumbers.map((pageNumber) => (
          <Button
            key={pageNumber}
            type="button"
            variant={pageNumber === page ? 'default' : 'outline'}
            size="sm"
            className="min-w-9 px-2"
            onClick={() => onPageChange(pageNumber)}
            aria-label={`${itemLabel} page ${pageNumber}`}
            aria-current={pageNumber === page ? 'page' : undefined}
          >
            {pageNumber}
          </Button>
        ))}
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => onPageChange(page + 1)}
          disabled={page >= pages}
          aria-label={`Next ${itemLabel} page`}
        >
          Next
          <ChevronRight className="size-4" aria-hidden="true" />
        </Button>
      </div>
    </nav>
  )
}
