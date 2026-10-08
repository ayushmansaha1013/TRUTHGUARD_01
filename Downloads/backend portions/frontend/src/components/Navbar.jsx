import { NavLink, useNavigate } from 'react-router-dom'
import { useEffect, useRef, useState } from 'react'
import { useAuth } from '../context/AuthContext.jsx'
import { useToast } from './Toast.jsx'

/**
 * Navbar — role-aware navigation with a scroll-reactive glass treatment.
 *
 * The "Dashboard" link is rendered ONLY for educators (layer-1 RBAC in the UI);
 * EducatorRoute + Supabase RLS remain the actual enforcement.
 *
 * HICK'S LAW: the nav shows at most three destinations, and only the ones this
 * role can actually reach. A student never has to read and reject a "Dashboard"
 * item — it simply isn't there, which removes a decision rather than adding a
 * disabled-looking option.
 *
 * The scroll listener is rAF-throttled and only flips a boolean at a 12px
 * threshold, so it does not re-render on every pixel of scroll.
 */
export default function Navbar() {
  const { user, role, isEducator, signOut, demoMode } = useAuth()
  const navigate = useNavigate()
  const toast = useToast()
  const [menuOpen, setMenuOpen] = useState(false)
  const [scrolled, setScrolled] = useState(false)
  const raf = useRef(0)

  useEffect(() => {
    const onScroll = () => {
      if (raf.current) return
      raf.current = requestAnimationFrame(() => {
        raf.current = 0
        setScrolled((window.scrollY || 0) > 12)
      })
    }
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => {
      window.removeEventListener('scroll', onScroll)
      cancelAnimationFrame(raf.current)
    }
  }, [])

  async function handleSignOut() {
    try {
      await signOut()
      toast.success('Signed out. Your session token was revoked.')
    } catch (err) {
      toast.error(`Could not sign out cleanly: ${err?.message ?? 'unknown error'}`)
    } finally {
      navigate('/login', { replace: true })
    }
  }

  // `press` adds the tactile push-in on :active — a physical confirmation that
  // is independent of colour, so it works for colour-blind users too.
  const linkClass = ({ isActive }) => `press ${isActive ? 'nav-link-active' : 'nav-link'}`

  return (
    <header
      className={`sticky top-0 z-40 border-b transition-all duration-300 ${
        scrolled
          ? 'bg-navy/85 backdrop-blur-xl border-navy-border shadow-[0_10px_30px_-20px_rgba(2,12,27,1)]'
          : 'bg-navy/40 backdrop-blur-md border-navy-border/50'
      }`}
    >
      <div className="max-w-6xl mx-auto px-4 h-16 flex items-center justify-between gap-4">
        {/* Brand */}
        <NavLink
          to={isEducator ? '/dashboard' : '/scanner'}
          className="flex items-center gap-2 group press"
        >
          <span className="w-9 h-9 grid place-items-center rounded-lg border border-teal/30 bg-teal/10 text-teal font-bold text-lg group-hover:bg-teal/20 transition">
            T
          </span>
          <span className="font-display font-semibold tracking-tight">
            Truth<span className="text-teal">Guard</span>
            <span className="text-ink-muted text-xs ml-2 hidden sm:inline">AI</span>
          </span>
        </NavLink>

        {/* Desktop nav */}
        <nav className="hidden md:flex items-center gap-1">
          <NavLink to="/scanner" className={linkClass}>
            Image Scanner
          </NavLink>
          <NavLink to="/fact-checker" className={linkClass}>
            Fact Checker
          </NavLink>
          {isEducator && (
            <NavLink to="/dashboard" className={linkClass}>
              Educator Dashboard
            </NavLink>
          )}
        </nav>

        {/* Right side */}
        <div className="flex items-center gap-3">
          {demoMode && (
            <span
              className="hidden lg:inline text-[11px] px-2 py-1 rounded border border-warn/40 text-warn bg-warn/10"
              title="VITE_DEMO_MODE=true — auth disabled for a visual demo"
            >
              DEMO MODE
            </span>
          )}

          <div className="hidden sm:flex flex-col items-end leading-tight">
            <span className="text-sm text-ink max-w-[180px] truncate">{user?.email ?? 'demo user'}</span>
            <span className="text-[11px] uppercase tracking-wider text-teal/80">{role ?? 'guest'}</span>
          </div>

          <button type="button" onClick={handleSignOut} className="btn-ghost press !py-2 !px-3 text-sm">
            Sign out
          </button>

          {/* Mobile menu toggle */}
          <button
            type="button"
            className="md:hidden btn-ghost press !py-2 !px-3"
            onClick={() => setMenuOpen((v) => !v)}
            aria-expanded={menuOpen}
            aria-label="Toggle navigation"
          >
            ☰
          </button>
        </div>
      </div>

      {/* Mobile nav */}
      {menuOpen && (
        <nav className="md:hidden border-t border-navy-border bg-navy-card/95 px-4 py-3 flex flex-col gap-1 animate-fade-up">
          <NavLink to="/scanner" className={linkClass} onClick={() => setMenuOpen(false)}>
            Image Scanner
          </NavLink>
          <NavLink to="/fact-checker" className={linkClass} onClick={() => setMenuOpen(false)}>
            Fact Checker
          </NavLink>
          {isEducator && (
            <NavLink to="/dashboard" className={linkClass} onClick={() => setMenuOpen(false)}>
              Educator Dashboard
            </NavLink>
          )}
        </nav>
      )}
    </header>
  )
}
