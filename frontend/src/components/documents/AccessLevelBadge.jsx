import { cn } from '@/lib/utils'
import { ACCESS_LEVEL_META } from '@/lib/documents'

export function AccessLevelBadge({ accessLevel, short = false, className }) {
  const meta = ACCESS_LEVEL_META[accessLevel] ?? {
    label: 'No access',
    shortLabel: 'None',
    tone: 'bg-muted text-muted-foreground ring-border',
  }

  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium ring-1 ring-inset',
        meta.tone,
        className,
      )}
    >
      {short ? meta.shortLabel : meta.label}
    </span>
  )
}
