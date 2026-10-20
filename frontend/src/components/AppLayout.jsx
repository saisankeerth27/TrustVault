import { FileText, LayoutDashboard, LogOut, ScrollText, Share2, ShieldCheck } from 'lucide-react'
import { useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '@/auth/useAuth'
import { BrandMark } from '@/components/BrandMark'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { formatRole } from '@/lib/roles'

const baseNavItems = [
  { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/documents', label: 'Documents', icon: FileText },
  { to: '/shared-with-me', label: 'Shared', icon: Share2 },
]

const adminNavItems = [
  { to: '/admin', label: 'Admin', icon: ShieldCheck },
  { to: '/admin/audit', label: 'Audit', icon: ScrollText },
]

export function AppLayout() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [isSigningOut, setIsSigningOut] = useState(false)

  const navItems =
    user?.role === 'ADMINISTRATOR' ? [...baseNavItems, ...adminNavItems] : baseNavItems

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
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-40 border-b bg-background/85 backdrop-blur">
        <div className="mx-auto flex h-16 w-full max-w-6xl items-center justify-between gap-4 px-4 sm:px-6">
          <BrandMark />
          <div className="flex items-center gap-2 sm:gap-3">
            <nav aria-label="Main navigation" className="flex items-center gap-1">
              {navItems.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.to === '/admin'}
                  className={({ isActive }) =>
                    cn(
                      'inline-flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background',
                      isActive
                        ? 'bg-accent text-accent-foreground'
                        : 'text-muted-foreground hover:bg-muted hover:text-foreground',
                    )
                  }
                >
                  <item.icon className="size-4" aria-hidden="true" />
                  <span className="hidden sm:inline">{item.label}</span>
                </NavLink>
              ))}
            </nav>

            <div className="hidden max-w-44 text-right lg:block">
              <p className="truncate text-sm font-medium">{user?.name}</p>
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
            >
              <LogOut className="size-4" aria-hidden="true" />
              <span className="hidden sm:inline">
                {isSigningOut ? 'Signing out...' : 'Sign out'}
              </span>
            </Button>
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8 sm:px-6 lg:py-12">
        <Outlet />
      </main>

      <footer className="border-t bg-muted/40">
        <div className="mx-auto flex w-full max-w-6xl flex-col gap-2 px-4 py-6 text-xs text-muted-foreground sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <p>TrustVault &mdash; Phase 7 tamper-evident audit trail</p>
          <p>Administrator audit history, signed checkpoints, and integrity verification.</p>
        </div>
      </footer>
    </div>
  )
}
