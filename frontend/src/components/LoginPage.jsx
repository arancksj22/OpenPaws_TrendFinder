import { useState } from 'react'
import { Button } from './ui/button'
import { AlertTriangle, Eye, EyeOff, CheckCircle2 } from 'lucide-react'

const BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

export default function LoginPage({ onLogin }) {
  const [mode, setMode]           = useState('signin') // 'signin' | 'signup'
  const [email, setEmail]         = useState('')
  const [password, setPassword]   = useState('')
  const [confirm, setConfirm]     = useState('')
  const [showPw, setShowPw]       = useState(false)
  const [loading, setLoading]     = useState(false)
  const [error, setError]         = useState(null)
  const [success, setSuccess]     = useState(null)

  const switchMode = (m) => {
    setMode(m)
    setError(null)
    setSuccess(null)
    setPassword('')
    setConfirm('')
  }

  const handleSignIn = async (e) => {
    e.preventDefault()
    if (!email || !password) { setError('Please enter your email and password.'); return }
    setLoading(true); setError(null)
    try {
      const res = await fetch(`${BASE_URL}/api/v1/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      })
      const data = await res.json()
      if (!res.ok) { setError(data.detail || 'Invalid email or password.'); return }
      localStorage.setItem('openpaws_jwt', data.access_token)
      localStorage.setItem('openpaws_user', JSON.stringify(data.user))
      onLogin(data.access_token, data.user)
    } catch {
      setError('Could not reach the server. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  const handleSignUp = async (e) => {
    e.preventDefault()
    if (!email || !password || !confirm) { setError('Please fill in all fields.'); return }
    if (password.length < 8) { setError('Password must be at least 8 characters.'); return }
    if (password !== confirm) { setError('Passwords do not match.'); return }
    setLoading(true); setError(null); setSuccess(null)
    try {
      const res = await fetch(`${BASE_URL}/api/v1/auth/signup`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      })
      const data = await res.json()

      // 202 means Supabase requires email confirmation
      if (res.status === 202 && data.detail === 'confirm_email') {
        setSuccess('Account created! Check your email to confirm your address, then sign in.')
        return
      }
      if (!res.ok) { setError(data.detail || 'Sign up failed. Please try again.'); return }

      // Auto-login on success
      localStorage.setItem('openpaws_jwt', data.access_token)
      localStorage.setItem('openpaws_user', JSON.stringify(data.user))
      onLogin(data.access_token, data.user)
    } catch {
      setError('Could not reach the server. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-background flex flex-col items-center justify-center px-4">
      <div className="w-full max-w-sm bg-card border border-border rounded-2xl shadow-sm overflow-hidden">

        {/* Logo + title */}
        <div className="flex flex-col items-center pt-10 pb-6 px-8 border-b border-border">
          <img src="/openpawslogo.png" alt="Open Paws" className="h-16 w-auto mb-4" />
          <h1 className="text-lg font-semibold text-foreground tracking-tight">Open Paws TrendFinder</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            {mode === 'signin' ? 'Sign in to your account' : 'Create your account'}
          </p>
          <div className="mt-4 text-[11px] text-muted-foreground text-center bg-secondary/50 rounded-lg p-2.5 w-full border border-border/50">
            <span className="font-semibold block mb-1 tracking-wider text-foreground">TEST LOGIN IS</span>
            <span className="font-mono">test@openpaws.org</span><br/>
            <span className="font-mono">password123</span>
          </div>
        </div>

        {/* Tab switcher */}
        <div className="flex border-b border-border">
          {[['signin', 'Sign In'], ['signup', 'Sign Up']].map(([id, label]) => (
            <button
              key={id}
              type="button"
              onClick={() => switchMode(id)}
              className={`flex-1 py-2.5 text-sm font-medium transition-all duration-150 ${
                mode === id
                  ? 'text-primary border-b-2 border-primary'
                  : 'text-muted-foreground hover:text-foreground border-b-2 border-transparent'
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        {/* Form */}
        <form onSubmit={mode === 'signin' ? handleSignIn : handleSignUp} className="px-8 py-7 flex flex-col gap-4">

          {/* Error */}
          {error && (
            <div className="flex items-start gap-2.5 text-xs text-destructive bg-destructive/5 rounded-xl p-3">
              <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {/* Success */}
          {success && (
            <div className="flex items-start gap-2.5 text-xs text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-xl p-3">
              <CheckCircle2 className="w-3.5 h-3.5 mt-0.5 shrink-0" />
              <span>{success}</span>
            </div>
          )}

          {/* Email */}
          <div className="flex flex-col gap-1.5">
            <label htmlFor="auth-email" className="text-xs font-medium text-foreground">Email</label>
            <input
              id="auth-email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={e => setEmail(e.target.value)}
              placeholder="you@example.com"
              className="h-9 w-full rounded-lg border border-border bg-secondary px-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary transition-all"
            />
          </div>

          {/* Password */}
          <div className="flex flex-col gap-1.5">
            <label htmlFor="auth-password" className="text-xs font-medium text-foreground">Password</label>
            <div className="relative">
              <input
                id="auth-password"
                type={showPw ? 'text' : 'password'}
                autoComplete={mode === 'signin' ? 'current-password' : 'new-password'}
                required
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="••••••••"
                className="h-9 w-full rounded-lg border border-border bg-secondary px-3 pr-9 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary transition-all"
              />
              <button
                type="button"
                onClick={() => setShowPw(v => !v)}
                tabIndex={-1}
                className="absolute inset-y-0 right-0 flex items-center px-3 text-muted-foreground hover:text-foreground transition-colors"
                aria-label={showPw ? 'Hide password' : 'Show password'}
              >
                {showPw ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
              </button>
            </div>
            {mode === 'signup' && (
              <p className="text-[11px] text-muted-foreground">Minimum 8 characters.</p>
            )}
          </div>

          {/* Confirm password — only on signup */}
          {mode === 'signup' && (
            <div className="flex flex-col gap-1.5">
              <label htmlFor="auth-confirm" className="text-xs font-medium text-foreground">Confirm Password</label>
              <input
                id="auth-confirm"
                type={showPw ? 'text' : 'password'}
                autoComplete="new-password"
                required
                value={confirm}
                onChange={e => setConfirm(e.target.value)}
                placeholder="••••••••"
                className="h-9 w-full rounded-lg border border-border bg-secondary px-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary transition-all"
              />
            </div>
          )}

          {/* Submit */}
          <Button type="submit" className="w-full mt-1" disabled={loading}>
            {loading ? (
              <span className="flex items-center gap-2">
                <span className="spinner w-3.5 h-3.5 border-white/30 border-t-white" />
                {mode === 'signin' ? 'Signing in…' : 'Creating account…'}
              </span>
            ) : mode === 'signin' ? 'Sign In' : 'Create Account'}
          </Button>
        </form>

        {/* Footer */}
        <p className="text-center text-xs text-muted-foreground pb-7 px-8">
          {mode === 'signin'
            ? "Don't have an account? "
            : 'Already have an account? '}
          <button
            type="button"
            onClick={() => switchMode(mode === 'signin' ? 'signup' : 'signin')}
            className="text-primary hover:underline font-medium"
          >
            {mode === 'signin' ? 'Sign up' : 'Sign in'}
          </button>
        </p>
      </div>
    </div>
  )
}
