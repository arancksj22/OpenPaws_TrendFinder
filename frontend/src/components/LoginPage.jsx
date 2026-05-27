import { useState } from 'react'
import { Button } from './ui/button'
import { AlertTriangle, Eye, EyeOff } from 'lucide-react'

export default function LoginPage({ onLogin }) {
  const [email, setEmail]       = useState('')
  const [password, setPassword] = useState('')
  const [showPw, setShowPw]     = useState(false)
  const [loading, setLoading]   = useState(false)
  const [error, setError]       = useState(null)

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!email || !password) {
      setError('Please enter your email and password.')
      return
    }
    setLoading(true)
    setError(null)
    try {
      const res = await fetch('/api/v1/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      })
      const data = await res.json()
      if (!res.ok) {
        setError(data.detail || 'Invalid email or password.')
        return
      }
      // Persist session
      localStorage.setItem('openpaws_jwt', data.access_token)
      localStorage.setItem('openpaws_user', JSON.stringify(data.user))
      onLogin(data.access_token, data.user)
    } catch (e) {
      setError('Could not reach the server. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-background flex flex-col items-center justify-center px-4">
      {/* Card */}
      <div className="w-full max-w-sm bg-card border border-border rounded-2xl shadow-sm overflow-hidden">
        {/* Header */}
        <div className="flex flex-col items-center pt-10 pb-6 px-8 border-b border-border">
          <img
            src="/openpawslogo.png"
            alt="OpenPaws"
            className="h-12 w-auto mb-4"
          />
          <h1 className="text-lg font-semibold text-foreground tracking-tight">OpenPaws TrendFinder</h1>
          <p className="text-sm text-muted-foreground mt-0.5">Sign in to your account</p>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="px-8 py-7 flex flex-col gap-4">
          {/* Error */}
          {error && (
            <div className="flex items-start gap-2.5 text-xs text-destructive bg-destructive/5 rounded-xl p-3">
              <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {/* Email */}
          <div className="flex flex-col gap-1.5">
            <label htmlFor="login-email" className="text-xs font-medium text-foreground">
              Email
            </label>
            <input
              id="login-email"
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
            <label htmlFor="login-password" className="text-xs font-medium text-foreground">
              Password
            </label>
            <div className="relative">
              <input
                id="login-password"
                type={showPw ? 'text' : 'password'}
                autoComplete="current-password"
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
          </div>

          {/* Submit */}
          <Button
            type="submit"
            className="w-full mt-1"
            disabled={loading}
          >
            {loading ? (
              <span className="flex items-center gap-2">
                <span className="spinner w-3.5 h-3.5 border-white/30 border-t-white" />
                Signing in…
              </span>
            ) : 'Sign In'}
          </Button>
        </form>

        {/* Footer note */}
        <p className="text-center text-xs text-muted-foreground pb-7 px-8">
          Account access is managed by your OpenPaws administrator.
        </p>
      </div>
    </div>
  )
}
