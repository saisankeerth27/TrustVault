import { FileText, Upload } from 'lucide-react'
import { Link } from 'react-router-dom'
import { PageHeader } from '@/components/PageHeader'
import { Button } from '@/components/ui/button'
import { buttonVariants } from '@/components/ui/button-variants'
import { Card, CardContent } from '@/components/ui/card'

export function DocumentsPage() {
  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Documents"
        title="Documents"
        description="Upload, organize, search, and manage documents. Authentication is active, but this page remains an intentional empty state until document APIs arrive."
        actions={
          <Button disabled title="Uploads are implemented in Phase 4">
            <Upload className="size-4" aria-hidden="true" />
            Upload in Phase 4
          </Button>
        }
      />

      <Card>
        <CardContent className="flex flex-col items-center justify-center gap-4 px-6 py-16 text-center">
          <span className="flex size-14 items-center justify-center rounded-2xl bg-muted text-muted-foreground">
            <FileText className="size-7" aria-hidden="true" />
          </span>
          <div className="space-y-2">
            <h2 className="text-lg font-semibold tracking-tight">No documents to show</h2>
            <p className="mx-auto max-w-md text-sm leading-6 text-muted-foreground">
              Document uploads, storage, search, and per-document permissions are planned for
              Phases 4 through 6. Your authenticated session does not expose document data yet,
              and no sample or fake documents are displayed here.
            </p>
          </div>
          <Link to="/dashboard" className={buttonVariants({ variant: 'outline' })}>
            Return to dashboard
          </Link>
        </CardContent>
      </Card>
    </div>
  )
}
