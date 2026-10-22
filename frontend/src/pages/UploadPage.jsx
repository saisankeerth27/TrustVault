import { ArrowLeft } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'
import { UploadDocumentPanel } from '@/components/documents/UploadDocumentPanel'
import { PageHeader } from '@/components/PageHeader'
import { buttonVariants } from '@/components/ui/button-variants'

export function UploadPage() {
  const navigate = useNavigate()

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Upload"
        title="Upload a document"
        description="Add a document to the private vault. The backend validates the file content, computes its checksum, stores it under a generated key, and records the upload in the audit trail."
        actions={
          <Link to="/documents" className={buttonVariants({ variant: 'outline' })}>
            <ArrowLeft className="size-4" aria-hidden="true" />
            Back to library
          </Link>
        }
      />

      <UploadDocumentPanel onCancel={() => navigate('/documents')} />
    </div>
  )
}
