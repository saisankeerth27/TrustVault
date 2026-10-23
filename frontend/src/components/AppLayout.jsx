import {
  FileText,
  LayoutDashboard,
  LogOut,
  ScrollText,
  Share2,
  ShieldCheck,
  UploadCloud,
} from 'lucide-react'
import { useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '@/auth/useAuth'
import { BrandMark } from '@/components/BrandMark'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { formatRole } from '@/lib/roles'

const baseNavItems = [
  { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/documents', label: 'Documents', icon: FileText },
  { to: '/shared-with-me', label: 'Shared with me', icon: Share2, shortLabel: 'Shared' },
]

const uploadNavItem = {
  to: '/upload',
  label: 'Upload document',
  shortLabel: 'Upload',
  icon: UploadCloud,
  end: true,
}

const adminNavItems = [
  { to: '/admin', label: 'System oversight', icon: ShieldCheck, end: true },
  { to: '/admin/audit', label: 'Audit trail', icon: ScrollText, shortLabel: 'Audit' },
]

function NavItems({ items, compact = false }) {
  return items.map((item) => (
    <NavLink
      key={item.to}
      to={item.to}
      end={item.end}
      aria-label={compact ? item.label : undefined}
      title={compact ? item.label : undefined}
      className={({ isActive }) =>
        cn(
          'inline-flex items-center rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background',
          compact
            ? 'shrink-0 gap-1.5 px-2.5 py-2 text-xs whitespace-nowrap'
            : 'w-full gap-3 px-3 py-2.5',
          isActive
            ? 'bg-accent text-accent-foreground'
            : 'text-muted-foreground hover:bg-muted hover:text-foreground',
        )
      }
    >
      <item.icon className="size-4 shrink-0" aria-hidden="true" />
      <span>{compact ? (item.shortLabel ?? item.label) : item.label}</span>
    </NavLink>
  ))
}

export function AppLayout() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [isSigningOut, setIsSigningOut] = useState(false)

  const workspaceItems = [...baseNavItems, uploadNavItem]
  const navItems =
    user?.role === 'ADMINISTRATOR' ? [...workspaceItems, ...adminNavItems] : workspaceItems

  async function handleSignOut() {
    setIsSigningOut(true)
    try {
      await logout()
    } catch {
      // The local session is still cleared by AuthProvider.
    } finally {
      setIsSigningOut(false)
      navigate('/login', { replace: true })
    }
  }

  return (
    <div className="min-h-screen bg-background lg:grid lg:grid-cols-[17rem_minmax(0,1fr)]">
      <aside className="hidden border-r bg-card/60 lg:sticky lg:top-0 lg:flex lg:h-screen lg:flex-col">
        <div className="border-b px-5 py-5">
          <BrandMark />
        </div>

        <nav aria-label="Main navigation" className="flex-1 space-y-1 overflow-y-auto p-3">
          <p className="px-3 pb-2 text-[10px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">
            Workspace
          </p>
          <NavItems items={workspaceItems} />

          {user?.role === 'ADMINISTRATOR' ? (
            <>
              <p className="px-3 pt-5 pb-2 text-[10px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">
                Administration
              </p>
              <NavItems items={adminNavItems} />
            </>
          ) : null}
        </nav>

        <div className="space-y-3 border-t p-3">
          <div className="rounded-lg bg-muted/60 px-3 py-2.5">
            <p className="truncate text-sm font-medium">{user?.name}</p>
            <p className="text-xs text-muted-foreground">
              {user ? formatRole(user.role) : ''}
            </p>
          </div>
          <Button
            type="button"
            variant="outline"
            className="w-full justify-start"
            onClick={handleSignOut}
            disabled={isSigningOut}
            aria-label={isSigningOut ? 'Signing out' : 'Sign out'}
          >
            <LogOut className="size-4" aria-hidden="true" />
            {isSigningOut ? 'Signing out...' : 'Sign out'}
          </Button>
        </div>
      </aside>

      <div className="flex min-h-screen min-w-0 flex-col">
        <header className="sticky top-0 z-40 border-b bg-background/90 backdrop-blur lg:hidden">
          <div className="flex h-16 items-center justify-between gap-3 px-4 sm:px-6">
            <BrandMark compact />
            <div className="flex items-center gap-3">
              <div className="hidden text-right sm:block">
                <p className="max-w-44 truncate text-sm font-medium">{user?.name}</p>
                <p className="text-xs text-muted-foreground">
                  {user ? formatRole(user.role) : ''}
                </p>
              </div>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={handleSignOut}
                disabled={isSigningOut}
                aria-label={isSigningOut ? 'Signing out' : 'Sign out'}
              >
                <LogOut className="size-4" aria-hidden="true" />
                <span className="hidden sm:inline">
                  {isSigningOut ? 'Signing out...' : 'Sign out'}
                </span>
              </Button>
            </div>
          </div>

          <nav
            aria-label="Main navigation"
            className="flex gap-1 overflow-x-auto border-t px-3 py-2"
          >
            <NavItems items={navItems} compact />
          </nav>
        </header>

        <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8 sm:px-6 lg:px-8 lg:py-10">
          <Outlet />
        </main>

        <footer className="border-t bg-muted/40">
          <div className="mx-auto flex w-full max-w-6xl flex-col gap-2 px-4 py-6 text-xs text-muted-foreground sm:flex-row sm:items-center sm:justify-between sm:px-6 lg:px-8">
            <p>TrustVault &mdash; tamper-evident document sharing</p>
            <p>
              Administrator audit history, signed checkpoints, and integrity verification.
            </p>
          </div>
        </footer>
      </div>
    </div>
  )
}
