import { useEffect, useState } from 'react'
import { useForm } from 'react-hook-form'
import {
  ArrowLeft,
  Ban,
  Check,
  Clock3,
  KeyRound,
  LoaderCircle,
  RefreshCw,
  ShieldCheck,
  UserPlus,
} from 'lucide-react'
import { Link, useParams } from 'react-router-dom'
import { z } from 'zod'
import { AccessLevelBadge } from '@/components/documents/AccessLevelBadge'
import { PageHeader } from '@/components/PageHeader'
import { Button } from '@/components/ui/button'
import { buttonVariants } from '@/components/ui/button-variants'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  canManageDocumentPermissions,
  formatDateTime,
} from '@/lib/documents'
import { getApiErrorMessage } from '@/services/api'
import { getDocument } from '@/services/documents'
import {
  grantDocumentPermission,
  listDocumentPermissions,
  revokeDocumentPermission,
  updateDocumentPermission,
} from '@/services/permissions'

const grantSchema = z.object({
  email: z
    .string()
    .trim()
    .min(1, { message: 'Recipient email is required.' })
    .email({ message: 'Enter a valid email address.' }),
  permission: z.enum(['READ', 'EDIT']),
})

const fieldClassName =
  'flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-xs transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50'

function isAbortError(error) {
  return error?.code === 'ERR_CANCELED' || error?.name === 'CanceledError'
}

function PermissionRow({ record, onChanged }) {
  const [level, setLevel] = useState(record.permission)
  const [isSaving, setIsSaving] = useState(false)
  const [isRevoking, setIsRevoking] = useState(false)
  const [confirmRevoke, setConfirmRevoke] = useState(false)
  const [rowError, setRowError] = useState(null)

  async function handleUpdate() {
    setRowError(null)
    setIsSaving(true)
    try {
      await updateDocumentPermission(record.document_id, record.id, level)
      onChanged(`${record.recipient_email} now has ${level} access.`)
    } catch (error) {
      setRowError(getApiErrorMessage(error))
    } finally {
      setIsSaving(false)
    }
  }

  async function handleRevoke() {
    setRowError(null)
    setIsRevoking(true)
    try {
      await revokeDocumentPermission(record.document_id, record.id)
      onChanged(`Access revoked for ${record.recipient_email}.`)
    } catch (error) {
      setRowError(getApiErrorMessage(error))
      setIsRevoking(false)
      setConfirmRevoke(false)
    }
  }

  return (
    <tr className="align-top">
      <td className="px-4 py-4">
        <p className="font-medium">{record.recipient_name}</p>
        <p className="mt-0.5 text-xs text-muted-foreground">{record.recipient_email}</p>
        {rowError ? (
          <p className="mt-2 max-w-64 text-xs text-destructive" role="alert">
            {rowError}
          </p>
        ) : null}
      </td>
      <td className="px-4 py-4">
        <label htmlFor={`permission-level-${record.id}`} className="sr-only">
          Access level for {record.recipient_email}
        </label>
        <select
          id={`permission-level-${record.id}`}
          value={level}
          onChange={(event) => setLevel(event.target.value)}
          disabled={isSaving || isRevoking}
          className="h-9 rounded-md border border-input bg-background px-2 text-sm shadow-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <option value="READ">Can view (READ)</option>
          <option value="EDIT">Can edit (EDIT)</option>
        </select>
        <div className="mt-2">
          <AccessLevelBadge accessLevel={record.permission} />
        </div>
      </td>
      <td className="px-4 py-4 text-muted-foreground">{formatDateTime(record.granted_at)}</td>
      <td className="px-4 py-4">
        <div className="flex flex-wrap items-center justify-end gap-2">
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={handleUpdate}
            disabled={isSaving || isRevoking || level === record.permission}
          >
            {isSaving ? (
              <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
            ) : (
              <Check className="size-4" aria-hidden="true" />
            )}
            {isSaving ? 'Saving...' : 'Save'}
          </Button>
          {confirmRevoke ? (
            <>
              <Button
                type="button"
                size="sm"
                variant="destructive"
                onClick={handleRevoke}
                disabled={isRevoking || isSaving}
              >
                {isRevoking ? (
                  <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
                ) : (
                  <Ban className="size-4" aria-hidden="true" />
                )}
                {isRevoking ? 'Revoking...' : 'Confirm revoke'}
              </Button>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                onClick={() => setConfirmRevoke(false)}
                disabled={isRevoking || isSaving}
              >
                Cancel
              </Button>
            </>
          ) : (
            <Button
              type="button"
              size="sm"
              variant="ghost"
              onClick={() => setConfirmRevoke(true)}
              disabled={isSaving || isRevoking}
            >
              <Ban className="size-4" aria-hidden="true" />
              Revoke
            </Button>
          )}
        </div>
      </td>
    </tr>
  )
}

export function DocumentPermissionsPage() {
  const { documentId } = useParams()
  const [documentRecord, setDocumentRecord] = useState(null)
  const [permissionData, setPermissionData] = useState(null)
  const [isLoading, setIsLoading] = useState(true)
  const [loadError, setLoadError] = useState(null)
  const [actionError, setActionError] = useState(null)
  const [notice, setNotice] = useState(null)
  const [refreshKey, setRefreshKey] = useState(0)
  const {
    register,
    handleSubmit,
    reset,
    setError,
    clearErrors,
    formState: { errors, isSubmitting },
  } = useForm({
    defaultValues: { email: '', permission: 'READ' },
  })

  useEffect(() => {
    const controller = new AbortController()

    async function load() {
      setIsLoading(true)
      setLoadError(null)
      try {
        const documentPayload = await getDocument(documentId, controller.signal)
        if (controller.signal.aborted) {
          return
        }
        setDocumentRecord(documentPayload)

        if (!canManageDocumentPermissions(documentPayload)) {
          setPermissionData(null)
          return
        }

        const permissionsPayload = await listDocumentPermissions(
          documentId,
          controller.signal,
        )
        if (!controller.signal.aborted) {
          setPermissionData(permissionsPayload)
        }
      } catch (error) {
        if (!isAbortError(error)) {
          setLoadError(error)
        }
      } finally {
        if (!controller.signal.aborted) {
          setIsLoading(false)
        }
      }
    }

    load()
    return () => controller.abort()
  }, [documentId, refreshKey])

  function handleChanged(message) {
    setActionError(null)
    setNotice(message)
    setRefreshKey((key) => key + 1)
  }

  const onGrant = async (values) => {
    setActionError(null)
    setNotice(null)

    const result = grantSchema.safeParse(values)
    if (!result.success) {
      clearErrors()
      for (const issue of result.error.issues) {
        const field = issue.path[0]
        if (field === 'email' || field === 'permission') {
          setError(field, { type: 'manual', message: issue.message })
        }
      }
      return
    }

    try {
      const record = await grantDocumentPermission(documentId, result.data)
      reset({ email: '', permission: 'READ' })
      setNotice(`${record.recipient_email} now has ${record.permission} access.`)
      setRefreshKey((key) => key + 1)
    } catch (error) {
      setActionError(getApiErrorMessage(error))
    }
  }

  if (isLoading) {
    return (
      <div className="flex min-h-80 items-center justify-center gap-3 text-sm text-muted-foreground">
        <LoaderCircle className="size-5 animate-spin" aria-hidden="true" />
        Loading sharing settings...
      </div>
    )
  }

  if (loadError?.response?.status === 404) {
    return (
      <div className="flex flex-col items-center justify-center gap-6 py-20 text-center">
        <span className="flex size-16 items-center justify-center rounded-2xl bg-muted text-muted-foreground">
          <KeyRound className="size-8" aria-hidden="true" />
        </span>
        <div className="space-y-3">
          <p className="text-xs font-semibold tracking-[0.2em] text-primary uppercase">
            Sharing unavailable
          </p>
          <h1 className="text-3xl font-semibold tracking-tight">Document not found</h1>
          <p className="mx-auto max-w-md text-sm leading-6 text-muted-foreground">
            The document does not exist, was deleted, or is not visible to your account.
          </p>
        </div>
        <Link to="/documents" className={buttonVariants({ variant: 'outline' })}>
          <ArrowLeft className="size-4" aria-hidden="true" />
          Back to documents
        </Link>
      </div>
    )
  }

  if (loadError) {
    return (
      <div
        role="alert"
        className="flex flex-col items-start gap-4 rounded-lg border border-destructive/30 bg-destructive/5 px-6 py-6 text-sm text-destructive"
      >
        <p>{getApiErrorMessage(loadError)}</p>
        <Button
          type="button"
          variant="outline"
          onClick={() => setRefreshKey((key) => key + 1)}
        >
          <RefreshCw className="size-4" aria-hidden="true" />
          Retry
        </Button>
      </div>
    )
  }

  if (!canManageDocumentPermissions(documentRecord)) {
    return (
      <div className="flex flex-col items-center justify-center gap-6 py-20 text-center">
        <span className="flex size-16 items-center justify-center rounded-2xl bg-destructive/10 text-destructive">
          <ShieldCheck className="size-8" aria-hidden="true" />
        </span>
        <div className="space-y-3">
          <p className="text-xs font-semibold tracking-[0.2em] text-destructive uppercase">
            Owner only
          </p>
          <h1 className="text-3xl font-semibold tracking-tight">Sharing is restricted</h1>
          <p className="mx-auto max-w-md text-sm leading-6 text-muted-foreground">
            Only the document owner can grant, change, or revoke access. Your current access level
            does not allow permission management.
          </p>
        </div>
        <Link
          to={`/documents/${documentId}`}
          className={buttonVariants({ variant: 'outline' })}
        >
          <ArrowLeft className="size-4" aria-hidden="true" />
          Back to document
        </Link>
      </div>
    )
  }

  const activePermissions =
    permissionData?.items.filter((item) => item.status === 'ACTIVE') ?? []
  const permissionHistory =
    permissionData?.items.filter((item) => item.status === 'REVOKED') ?? []

  return (
    <div className="space-y-8">
      <Link
        to={`/documents/${documentId}`}
        className="inline-flex items-center gap-2 text-sm font-medium text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" aria-hidden="true" />
        Back to document
      </Link>

      <PageHeader
        eyebrow="Sharing"
        title="Manage access"
        description={
          documentRecord
            ? `Grant READ or EDIT access to ${documentRecord.name}. Changes are enforced by the backend on the recipient's next request.`
            : 'Grant or revoke document access.'
        }
        actions={
          <AccessLevelBadge accessLevel={documentRecord?.access_level} />
        }
      />

      <div className="grid gap-5 lg:grid-cols-[1.4fr_1fr]">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <UserPlus className="size-4 text-primary" aria-hidden="true" />
              Grant access
            </CardTitle>
          </CardHeader>
          <CardContent>
            <form className="grid gap-5" onSubmit={handleSubmit(onGrant)}>
              <div className="space-y-2">
                <label htmlFor="grant-email" className="text-sm font-medium">
                  Recipient email
                </label>
                <input
                  id="grant-email"
                  type="email"
                  autoComplete="off"
                  placeholder="teammate@example.com"
                  className={fieldClassName}
                  disabled={isSubmitting}
                  aria-invalid={errors.email ? true : undefined}
                  aria-describedby={errors.email ? 'grant-email-error' : 'grant-email-help'}
                  {...register('email')}
                />
                <p id="grant-email-help" className="text-xs text-muted-foreground">
                  The recipient must already have an active TrustVault account.
                </p>
                {errors.email ? (
                  <p id="grant-email-error" className="text-sm text-destructive">
                    {errors.email.message}
                  </p>
                ) : null}
              </div>

              <div className="space-y-2">
                <label htmlFor="grant-permission" className="text-sm font-medium">
                  Access level
                </label>
                <select
                  id="grant-permission"
                  className={fieldClassName}
                  disabled={isSubmitting}
                  aria-invalid={errors.permission ? true : undefined}
                  {...register('permission')}
                >
                  <option value="READ">Can view (READ)</option>
                  <option value="EDIT">Can edit (EDIT)</option>
                </select>
                {errors.permission ? (
                  <p className="text-sm text-destructive">{errors.permission.message}</p>
                ) : null}
              </div>

              <Button type="submit" disabled={isSubmitting} className="w-fit">
                {isSubmitting ? (
                  <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
                ) : (
                  <UserPlus className="size-4" aria-hidden="true" />
                )}
                {isSubmitting ? 'Granting...' : 'Grant access'}
              </Button>
            </form>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>How access works</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm leading-6 text-muted-foreground">
            <div className="flex items-start gap-3">
              <KeyRound className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden="true" />
              <p>
                READ allows metadata and downloads. EDIT also allows metadata updates. Only the
                owner can delete the document or manage access.
              </p>
            </div>
            <p>
              Administrators can review metadata across the library, but cannot read document
              content without an explicit grant.
            </p>
            <p>
              Revocation is immediate and retained in the grant history. Regranting creates a new
              active grant.
            </p>
          </CardContent>
        </Card>
      </div>

      {notice ? (
        <div
          role="status"
          className="rounded-lg border border-emerald-200 bg-emerald-50/70 px-4 py-3 text-sm text-emerald-900"
        >
          {notice}
        </div>
      ) : null}

      {actionError ? (
        <div
          role="alert"
          className="rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive"
        >
          {actionError}
        </div>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>
            People with access
            <span className="ml-2 text-sm font-normal text-muted-foreground">
              {permissionData?.active_total ?? 0}
            </span>
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {activePermissions.length === 0 ? (
            <div className="flex flex-col items-center gap-2 px-6 py-10 text-center">
              <KeyRound className="size-6 text-muted-foreground" aria-hidden="true" />
              <p className="font-medium">No active shares</p>
              <p className="max-w-md text-sm text-muted-foreground">
                This document is currently visible only to you and metadata-only administrators.
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[760px] text-sm">
                <thead className="border-y bg-muted/40 text-left text-xs tracking-wide text-muted-foreground uppercase">
                  <tr>
                    <th scope="col" className="px-6 py-3 font-medium">
                      Recipient
                    </th>
                    <th scope="col" className="px-4 py-3 font-medium">
                      Current / new level
                    </th>
                    <th scope="col" className="px-4 py-3 font-medium">
                      Granted
                    </th>
                    <th scope="col" className="px-6 py-3 text-right font-medium">
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {activePermissions.map((record) => (
                    <PermissionRow
                      key={record.id}
                      record={record}
                      onChanged={handleChanged}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {permissionHistory.length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Clock3 className="size-4 text-muted-foreground" aria-hidden="true" />
              Grant history
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[680px] text-sm">
                <thead className="border-y bg-muted/40 text-left text-xs tracking-wide text-muted-foreground uppercase">
                  <tr>
                    <th scope="col" className="px-6 py-3 font-medium">
                      Recipient
                    </th>
                    <th scope="col" className="px-4 py-3 font-medium">
                      Level
                    </th>
                    <th scope="col" className="px-4 py-3 font-medium">
                      Granted
                    </th>
                    <th scope="col" className="px-4 py-3 font-medium">
                      Revoked
                    </th>
                    <th scope="col" className="px-6 py-3 font-medium">
                      Status
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {permissionHistory.map((record) => (
                    <tr key={record.id}>
                      <td className="px-6 py-4">
                        <p className="font-medium">{record.recipient_name}</p>
                        <p className="mt-0.5 text-xs text-muted-foreground">
                          {record.recipient_email}
                        </p>
                      </td>
                      <td className="px-4 py-4">
                        <AccessLevelBadge accessLevel={record.permission} />
                      </td>
                      <td className="px-4 py-4 text-muted-foreground">
                        {formatDateTime(record.granted_at)}
                      </td>
                      <td className="px-4 py-4 text-muted-foreground">
                        {formatDateTime(record.revoked_at)}
                      </td>
                      <td className="px-6 py-4">
                        <span className="inline-flex items-center rounded-full bg-muted px-2.5 py-1 text-xs font-medium text-muted-foreground">
                          Revoked
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      ) : null}
    </div>
  )
}
