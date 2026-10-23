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
        title="Upload a Document"
        description="Upload your document securely and manage who can access it. You can share it with specific users and control whether they can view or edit it."
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
