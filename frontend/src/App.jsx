import { useState, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import './App.css'
import LoginPage from './components/LoginPage'
import { Button } from './components/ui/button'
import { Card, CardContent, CardHeader, CardFooter } from './components/ui/card'
import { Badge } from './components/ui/badge'
import { Progress } from './components/ui/progress'
import { Separator } from './components/ui/separator'
import { Collapsible, CollapsibleTrigger, CollapsibleContent } from './components/ui/collapsible'
import {
  RefreshCw, Play, Sparkles, ChevronDown, ExternalLink,
  Activity, TrendingUp, Heart, Shield, Star, AlertTriangle, Clock, Hash, LogOut,
  Copy, Check, Edit2, Download, Save, X, Bot
} from 'lucide-react'

const BASE_URL = import.meta.env.VITE_API_BASE_URL || ''
const API_BASE = `${BASE_URL}/api/v1/trends`
const HISTORY_API = `${BASE_URL}/api/v1/history`
const AUTH_API = `${BASE_URL}/api/v1/auth`

// ─── helpers ─────────────────────────────────────────────────────────────────

function postLink(post) {
  if (post.permalink) {
    if (post.permalink.startsWith('http')) return post.permalink
    return `https://reddit.com${post.permalink}`
  }
  if (post.url) return post.url
  return null
}

function shortId(id) {
  return id ? id.slice(0, 8) + '…' : '—'
}

function statusBadge(status) {
  const map = {
    pending_review: { label: 'Pending Review', variant: 'pending' },
    explainer_ready: { label: 'Explainer Ready', variant: 'ready' },
  }
  const s = map[status] || { label: status ?? 'Unknown', variant: 'outline' }
  return <Badge variant={s.variant}>{s.label}</Badge>
}

// ─── ScoreBar ─────────────────────────────────────────────────────────────────

function ScoreBar({ label, value, isComposite }) {
  const pct = Math.max(0, Math.min(100, value * 100))
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex justify-between items-center">
        <span className={`text-xs ${isComposite ? 'font-semibold text-foreground' : 'text-muted-foreground'}`}>
          {label}
        </span>
        <span className={`font-mono-data text-xs font-medium ${isComposite ? 'text-primary' : 'text-foreground'}`}>
          {pct.toFixed(1)}%
        </span>
      </div>
      <Progress
        value={pct}
        className={isComposite ? 'h-2' : 'h-1'}
        indicatorClassName={isComposite ? 'bg-primary' : 'bg-emerald-500'}
      />
    </div>
  )
}

// ─── DraftCard ───────────────────────────────────────────────────────────────

function DraftCard({ draft, metrics, trendId, jwtToken, onUpdateDraft }) {
  const { tone, text, char_count, hashtags, passed_boundary_check, boundary_issues, is_recommended, scores, index } = draft
  const [open, setOpen] = useState(false)
  const [copied, setCopied] = useState(false)
  const [isEditing, setIsEditing] = useState(false)
  const [editText, setEditText] = useState(text)
  const [isSaving, setIsSaving] = useState(false)

  const toneColors = {
    factual: 'bg-blue-50 text-blue-700',
    emotional: 'bg-rose-50 text-rose-700',
    call_to_action: 'bg-violet-50 text-violet-700',
  }

  const handleCopy = () => {
    navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const handleSave = async () => {
    if (!trendId || !jwtToken) return
    setIsSaving(true)
    try {
      const res = await fetch(`${API_BASE}/${trendId}/draft/${index}`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${jwtToken}`
        },
        body: JSON.stringify({ text: editText })
      })
      if (!res.ok) throw new Error('Failed to save draft')
      const updatedDraft = await res.json()
      if (onUpdateDraft) {
        onUpdateDraft(index, updatedDraft)
      }
      setIsEditing(false)
    } catch (e) {
      console.error(e)
      alert("Failed to save draft edit")
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <div className={`rounded-xl p-5 flex flex-col gap-4 transition-all duration-150
      ${is_recommended ? 'border-2 border-emerald-400 bg-emerald-500/5 shadow-sm' : 'border border-border bg-card'}
      ${!passed_boundary_check ? 'opacity-60' : ''}
    `}>
      <div className="flex items-center justify-between">
        <span className={`text-[11px] font-semibold uppercase tracking-wider px-2.5 py-1 rounded-full ${toneColors[tone] || 'bg-secondary text-secondary-foreground'}`}>
          {tone?.replace('_', ' ')}
        </span>
        <div className="flex items-center gap-2">
          {is_recommended && (
            <Badge variant="ready" className="gap-1">
              <Star className="w-3 h-3" /> Recommended
            </Badge>
          )}
          {!passed_boundary_check && (
            <Badge variant="destructive" className="gap-1">
              <AlertTriangle className="w-3 h-3" /> Boundary Failed
            </Badge>
          )}
          <div className="flex items-center gap-1 ml-2">
            {jwtToken && !isEditing && (
              <Button variant="ghost" size="icon" className="h-6 w-6 text-muted-foreground hover:text-foreground" onClick={() => { setIsEditing(true); setEditText(text); }}>
                <Edit2 className="w-3 h-3" />
              </Button>
            )}
            <Button variant="ghost" size="icon" className="h-6 w-6 text-muted-foreground hover:text-foreground" onClick={handleCopy}>
              {copied ? <Check className="w-3 h-3 text-emerald-500" /> : <Copy className="w-3 h-3" />}
            </Button>
          </div>
        </div>
      </div>

      {!passed_boundary_check && boundary_issues?.length > 0 && (
        <div className="text-xs text-destructive bg-destructive/5 rounded-lg p-3 flex flex-col gap-1">
          {boundary_issues.map((i, idx) => <div key={idx}>• {i}</div>)}
        </div>
      )}

      {isEditing ? (
        <div className="flex flex-col gap-2">
          <textarea
            value={editText}
            onChange={(e) => setEditText(e.target.value)}
            className="w-full min-h-[100px] p-3 text-sm rounded-md border border-input bg-background focus:outline-none focus:ring-2 focus:ring-primary/50 resize-y"
            disabled={isSaving}
          />
          <div className="flex justify-end gap-2 mt-1">
            <Button variant="outline" size="sm" onClick={() => setIsEditing(false)} disabled={isSaving}>
              <X className="w-3 h-3 mr-1" /> Cancel
            </Button>
            <Button variant="default" size="sm" onClick={handleSave} disabled={isSaving}>
              <Save className={`w-3 h-3 mr-1 ${isSaving ? 'animate-pulse' : ''}`} /> {isSaving ? 'Saving & Re-scoring...' : 'Save Edit'}
            </Button>
          </div>
        </div>
      ) : (
        <p className="text-sm leading-relaxed text-foreground whitespace-pre-wrap">{text}</p>
      )}

      <div className="flex items-center gap-3 text-xs text-muted-foreground">
        <span className="font-mono-data">{char_count}/300</span>
        {hashtags?.length > 0 && (
          <span className="flex items-center gap-1 text-primary">
            <Hash className="w-3 h-3" />
            {hashtags.map(h => `#${h}`).join(' ')}
          </span>
        )}
      </div>

      <Separator />

      <div className="flex flex-col gap-3">
        <ScoreBar label="Composite Score" value={scores.composite} isComposite={true} />
        <Collapsible open={open} onOpenChange={setOpen}>
          <CollapsibleTrigger className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors w-full text-left">
            <ChevronDown className={`w-3.5 h-3.5 transition-transform duration-200 ${open ? 'rotate-180' : ''}`} />
            {open ? 'Hide' : 'View'} individual metrics
          </CollapsibleTrigger>
          <CollapsibleContent>
            <div className="flex flex-col gap-2.5 mt-3">
              {metrics.map(m => (
                <ScoreBar key={m.key} label={m.label} value={scores[m.key] ?? 0} />
              ))}
            </div>
          </CollapsibleContent>
        </Collapsible>
      </div>
    </div>
  )
}

// ─── GenerationResultPanel ───────────────────────────────────────────────────

function GenerationResultPanel({ data, onRegenerateImage, regeneratingImage, trendId, jwtToken, onUpdateDraft }) {
  if (!data || !data.generation) return null
  const gen = data.generation
  const storage = data.storage

  const handleDownloadStrategy = () => {
    let html = `
      <html xmlns:o='urn:schemas-microsoft-com:office:office' xmlns:w='urn:schemas-microsoft-com:office:word' xmlns='http://www.w3.org/TR/REC-html40'>
      <head><meta charset='utf-8'><title>Campaign Strategy</title></head>
      <body style="font-family: Arial, sans-serif; line-height: 1.5;">
        <h1 style="color: #2F363D;">Campaign Strategy: ${trendId}</h1>
        <hr />
    `;
    if (gen.advocacy_brief) {
      html += `<h2 style="color: #2F363D;">Advocacy Brief</h2><p>${gen.advocacy_brief.replace(/\n/g, '<br>')}</p>`;
    }
    if (gen.scored_drafts) {
      html += `<h2 style="color: #2F363D;">Draft Posts</h2>`;
      gen.scored_drafts.forEach((d, i) => {
        html += `<h3 style="color: #0366D6;">Draft ${i + 1} (${d.tone})</h3>`;
        html += `<p>${d.text.replace(/\n/g, '<br>')}</p>`;
        if (d.hashtags?.length) html += `<p><strong>Hashtags:</strong> ${d.hashtags.map(h => '#' + h).join(' ')}</p>`;
        html += `<br/>`;
      })
    }
    html += `</body></html>`;
    const blob = new Blob([html], { type: 'application/msword' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `campaign-strategy-${shortId(trendId)}.doc`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  return (
    <div className="mt-4 flex flex-col gap-5">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Sparkles className="w-3.5 h-3.5 text-primary" />
          <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Generated Content</span>
        </div>
        <Button variant="outline" size="sm" className="h-7 text-xs gap-1.5" onClick={handleDownloadStrategy}>
          <Download className="w-3 h-3" /> Download Strategy
        </Button>
      </div>

      {storage?.image_url && (
        <div className="flex flex-col gap-2">
          <div className="overflow-hidden rounded-2xl border border-border shadow-sm relative group">
            <img src={storage.image_url} alt="Generated visual" className="w-full object-cover" loading="lazy" />
            {onRegenerateImage && (
              <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={onRegenerateImage}
                  disabled={regeneratingImage}
                  className="gap-2"
                >
                  <RefreshCw className={`w-4 h-4 ${regeneratingImage ? 'animate-spin' : ''}`} />
                  {regeneratingImage ? 'Regenerating...' : 'Regenerate Artwork'}
                </Button>
              </div>
            )}
          </div>
          {onRegenerateImage && (
            <p className="text-[10px] text-muted-foreground text-center">Hover to regenerate artwork</p>
          )}
        </div>
      )}

      <div className="flex flex-col gap-3">
        <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Scored Drafts</span>
        {gen.scored_drafts?.map(draft => (
          <DraftCard
            key={draft.index}
            draft={draft}
            metrics={gen.score_meta?.metrics || []}
            trendId={trendId}
            jwtToken={jwtToken}
            onUpdateDraft={onUpdateDraft}
          />
        ))}
      </div>
    </div>
  )
}

// ─── ExplainerPanel ──────────────────────────────────────────────────────────

function ExplainerPanel({ data }) {
  if (!data) return null
  return (
    <div className="mt-4 rounded-xl bg-emerald-50 border border-emerald-100 p-4 flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <Activity className="w-3.5 h-3.5 text-emerald-600" />
        <span className="text-xs font-semibold uppercase tracking-wider text-emerald-700">AI Explainer</span>
      </div>
      <p className="text-sm leading-relaxed text-gray-700">{data.explainer}</p>
    </div>
  )
}

// ─── TrendCard ───────────────────────────────────────────────────────────────

function TrendCard({ trend, jwtToken }) {
  const [loading, setLoading] = useState(false)
  const [genLoading, setGenLoading] = useState(false)
  const [regeneratingImage, setRegeneratingImage] = useState(false)
  const [explainer, setExplainer] = useState(
    trend.explainer
      ? {
        trend_id: trend.trend_id,
        explainer: trend.explainer,
        model_used: '—',
        prompt_tokens: null,
        completion_tokens: null,
      }
      : null
  )
  const [generation, setGeneration] = useState(null)
  const [error, setError] = useState(null)

  const getHeaders = () => {
    const h = { 'Content-Type': 'application/json' }
    if (jwtToken) h['Authorization'] = `Bearer ${jwtToken}`
    return h
  }

  const handleExplain = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`${API_BASE}/${trend.trend_id}/explainer`, {
        method: 'POST',
        headers: getHeaders()
      })
      if (!res.ok) {
        const body = await res.text()
        throw new Error(`${res.status} ${res.statusText}: ${body}`)
      }
      const data = await res.json()
      setExplainer(data)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [trend.trend_id, jwtToken])

  const handleGenerate = useCallback(async () => {
    setGenLoading(true)
    setError(null)
    try {
      const res = await fetch(`${API_BASE}/${trend.trend_id}/generate`, {
        method: 'POST',
        headers: getHeaders()
      })
      if (!res.ok) {
        const body = await res.text()
        throw new Error(`${res.status} ${res.statusText}: ${body}`)
      }
      const data = await res.json()
      setGeneration(data)
    } catch (e) {
      setError(e.message)
    } finally {
      setGenLoading(false)
    }
  }, [trend.trend_id, jwtToken])

  const handleRegenerateImage = useCallback(async () => {
    setRegeneratingImage(true)
    setError(null)
    try {
      const res = await fetch(`${API_BASE}/${trend.trend_id}/regenerate-image`, {
        method: 'POST',
        headers: getHeaders()
      })
      if (!res.ok) {
        const body = await res.text()
        throw new Error(`${res.status} ${res.statusText}: ${body}`)
      }
      const data = await res.json()
      setGeneration(prev => {
        if (!prev) return prev
        return {
          ...prev,
          storage: {
            ...prev.storage,
            image_url: data.image_url
          }
        }
      })
    } catch (e) {
      setError(e.message)
    } finally {
      setRegeneratingImage(false)
    }
  }, [trend.trend_id, jwtToken])

  const handleUpdateDraft = useCallback((draftIndex, updatedDraft) => {
    setGeneration(prev => {
      if (!prev || !prev.generation) return prev
      const newDrafts = [...prev.generation.scored_drafts]
      newDrafts[draftIndex] = {
        ...newDrafts[draftIndex],
        ...updatedDraft
      }
      return {
        ...prev,
        generation: {
          ...prev.generation,
          scored_drafts: newDrafts
        }
      }
    })
  }, [])

  const examplePosts = trend.example_posts?.slice(0, 5) ?? []

  return (
    <Card id={`trend-${trend.trend_id}`} className="flex flex-col gap-0 overflow-hidden p-0">
      {/* Header */}
      <CardHeader className="px-5 py-4 gap-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3 text-xs text-muted-foreground flex-wrap">
            <span className="flex items-center gap-1.5">
              <TrendingUp className="w-3.5 h-3.5 text-foreground" />
              <span className="font-medium text-foreground">{trend.representative_count ?? 0}</span> posts
            </span>
            <span>·</span>
            <span className="flex items-center gap-1">
              <Clock className="w-3 h-3" />
              {trend.created_at ? new Date(trend.created_at).toLocaleDateString() : '—'}
            </span>
          </div>
          {statusBadge(trend.status)}
        </div>
      </CardHeader>

      <Separator />

      {/* Example Posts */}
      {examplePosts.length > 0 && (
        <CardContent className="px-5 py-4">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mb-3">
            Top Example Posts
          </p>
          <ol className="flex flex-col gap-2">
            {examplePosts.map((post) => {
              const link = postLink(post)
              const label = post.title || post.text || post.body || post.id
              return (
                <motion.li
                  key={post.id}
                  whileHover={{ scale: 1.01 }}
                  transition={{ duration: 0.2, ease: "easeOut" }}
                  className="flex items-center gap-2 text-sm px-3 py-2 rounded-lg bg-secondary hover:bg-secondary/70 transition-colors group"
                >
                  <span className="text-[11px] font-semibold text-muted-foreground w-20 shrink-0 truncate">
                    {post.community}
                  </span>
                  {link ? (
                    <a
                      href={link}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex-1 text-foreground truncate hover:text-primary transition-colors flex items-center gap-1 min-w-0"
                    >
                      <span className="truncate">{label}</span>
                      <ExternalLink className="w-3 h-3 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity" />
                    </a>
                  ) : (
                    <span className="flex-1 text-muted-foreground truncate">{label}</span>
                  )}
                  <span className="text-[11px] font-mono-data text-muted-foreground shrink-0">↑{post.score ?? 0}</span>
                </motion.li>
              )
            })}
          </ol>
        </CardContent>
      )}

      <Separator />

      {/* Footer Buttons */}
      <CardFooter className="px-5 py-3 gap-2">
        <Button
          variant="secondary"
          size="sm"
          onClick={handleExplain}
          disabled={loading || genLoading}
          className="gap-1.5"
        >
          {loading
            ? <span className="spinner w-3.5 h-3.5" aria-label="Loading" />
            : <Activity className="w-3.5 h-3.5" />
          }
          Explain
        </Button>
        <Button
          size="sm"
          onClick={handleGenerate}
          disabled={loading || genLoading}
          title="Run Phase 7-10 Pipeline"
          className="gap-1.5"
        >
          {genLoading
            ? <span className="spinner w-3.5 h-3.5 border-white/30 border-t-white" aria-label="Generating" />
            : <Play className="w-3.5 h-3.5" />
          }
          Generate
        </Button>
        {error && (
          <p className="text-xs text-destructive flex items-center gap-1 ml-1">
            <AlertTriangle className="w-3 h-3" /> {error}
          </p>
        )}
      </CardFooter>

      {/* Explainer & Generation */}
      {(explainer || generation) && (
        <div className="px-5 pb-5 flex flex-col gap-0">
          <AnimatePresence initial={false}>
            {explainer && (
              <motion.div
                key="explainer"
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
                className="overflow-hidden"
              >
                <div className="pt-2 pb-2">
                  <ExplainerPanel data={explainer} />
                </div>
              </motion.div>
            )}
            {generation && (
              <motion.div
                key="generation"
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
                className="overflow-hidden"
              >
                <div className="pt-2">
                  <GenerationResultPanel
                    data={generation}
                    onRegenerateImage={handleRegenerateImage}
                    regeneratingImage={regeneratingImage}
                    trendId={trend.trend_id}
                    jwtToken={jwtToken}
                    onUpdateDraft={handleUpdateDraft}
                  />
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      )}
    </Card>
  )
}

// ─── HistoryItem ─────────────────────────────────────────────────────────────

function HistoryItem({ item }) {
  const mockData = {
    generation: {
      advocacy_brief: item.advocacy_brief,
      score_meta: {
        metrics: [
          { key: "text_performance", label: "Text Performance" },
          { key: "advocacy_preference", label: "Advocacy Preference" },
        ]
      },
      scored_drafts: item.scored_drafts,
    },
    storage: {
      image_url: item.image_url
    }
  }

  return (
    <Card className="overflow-hidden p-0">
      <CardHeader className="px-5 py-4">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium text-foreground">
            Saved Generation
          </span>
          <Badge variant="ready" className="gap-1">
            <Clock className="w-3 h-3" />
            Generated {new Date(item.created_at).toLocaleDateString()}
          </Badge>
        </div>
      </CardHeader>
      <Separator />
      <div className="px-5 pb-5">
        <GenerationResultPanel data={mockData} trendId={item.trend_id} />
      </div>
    </Card>
  )
}

// ─── App ─────────────────────────────────────────────────────────────────────

export default function App() {
  const [trends, setTrends] = useState([])
  const [history, setHistory] = useState([])
  const [count, setCount] = useState(0)
  const [loading, setLoading] = useState(true)
  const [pipelineLoading, setPipelineLoading] = useState(false)
  const [error, setError] = useState(null)

  const [statusFilter, setStatusFilter] = useState('pending_review')
  const [currentView, setCurrentView] = useState('trends')

  // ── Auth state ────────────────────────────────────────────────────────────
  const [authChecked, setAuthChecked] = useState(false) // has /me been called?
  const [authed, setAuthed] = useState(false)
  const [authToken, setAuthToken] = useState(null)
  const [authUser, setAuthUser] = useState(null)  // { id, email }
  const [showDiscordBanner, setShowDiscordBanner] = useState(true)

  // On mount: validate any stored token with /me
  useEffect(() => {
    let storedToken = localStorage.getItem('openpaws_jwt')
    
    // Parse Supabase hash fragment for email confirmation redirects
    const hash = window.location.hash.substring(1)
    if (hash) {
      const params = new URLSearchParams(hash)
      const hashToken = params.get('access_token')
      if (hashToken) {
        storedToken = hashToken
        localStorage.setItem('openpaws_jwt', hashToken)
        window.history.replaceState(null, null, window.location.pathname)
      }
    }

    if (!storedToken) { setAuthChecked(true); return }
    fetch(`${AUTH_API}/me`, {
      headers: { Authorization: `Bearer ${storedToken}` }
    })
      .then(res => {
        if (!res.ok) throw new Error('invalid')
        return res.json()
      })
      .then(data => {
        setAuthToken(storedToken)
        setAuthUser({ id: data.user_id, email: data.email })
        setAuthed(true)
      })
      .catch(() => {
        localStorage.removeItem('openpaws_jwt')
        localStorage.removeItem('openpaws_user')
      })
      .finally(() => setAuthChecked(true))
  }, [])

  const handleLogin = useCallback((token, user) => {
    setAuthToken(token)
    setAuthUser(user)
    setAuthed(true)
  }, [])

  const handleLogout = useCallback(async () => {
    try {
      await fetch(`${AUTH_API}/logout`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${authToken}` }
      })
    } catch (_) { /* non-fatal */ }
    localStorage.removeItem('openpaws_jwt')
    localStorage.removeItem('openpaws_user')
    setAuthToken(null)
    setAuthUser(null)
    setAuthed(false)
  }, [authToken])

  const getHeaders = useCallback(() => {
    const h = {}
    if (authToken) h['Authorization'] = `Bearer ${authToken}`
    return h
  }, [authToken])

  const loadTrends = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams({ limit: 20, offset: 0 })
      params.set('status', statusFilter)
      const res = await fetch(`${API_BASE}/?${params}`, { headers: getHeaders() })
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
      const data = await res.json()
      setTrends(data.trends ?? [])
      setCount(data.count ?? 0)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [statusFilter, getHeaders])

  const loadHistory = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`${HISTORY_API}/?limit=20`, { headers: getHeaders() })
      if (!res.ok) {
        if (res.status === 401) throw new Error('Session expired. Please log in again.')
        throw new Error(`${res.status} ${res.statusText}`)
      }
      const data = await res.json()
      setHistory(data.items ?? [])
      setCount(data.items?.length ?? 0)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [getHeaders])

  const handleTriggerPipeline = useCallback(async () => {
    setPipelineLoading(true)
    setError(null)
    try {
      const trigRes = await fetch(`${BASE_URL}/api/v1/pipeline/trigger`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...getHeaders() },
        body: JSON.stringify({ trigger: 'ui', async_run: false })
      })
      if (!trigRes.ok) throw new Error(`Trigger failed: ${trigRes.statusText}`)

      const discRes = await fetch(`${BASE_URL}/api/v1/pipeline/discover`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...getHeaders() },
        body: JSON.stringify({ drain: true })
      })
      if (!discRes.ok) throw new Error(`Discovery failed: ${discRes.statusText}`)

      await loadTrends()
    } catch (e) {
      setError(e.message)
    } finally {
      setPipelineLoading(false)
    }
  }, [getHeaders, loadTrends])

  useEffect(() => {
    if (currentView === 'trends') loadTrends()
    else if (currentView === 'history') loadHistory()
  }, [currentView, loadTrends, loadHistory])

  const tabs = [
    { id: 'trends', label: 'Trends' },
    { id: 'history', label: 'My History' },
  ]

  // ── Gates ─────────────────────────────────────────────────────────────────
  if (!authChecked) {
    // Waiting for /me check — show minimal loading screen
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <span className="spinner w-8 h-8" style={{ borderWidth: 3 }} />
      </div>
    )
  }

  if (!authed) {
    return <LoginPage onLogin={handleLogin} />
  }

  return (
    <div className="min-h-screen bg-background flex flex-col">
      {/* ── Header ── */}
      <header className="sticky top-0 z-50 bg-background/80 backdrop-blur-xl border-b border-border">
        <div className="max-w-6xl mx-auto px-6">
          {/* Top row */}
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center gap-3.5">
              <img
                src="/openpawslogo.png"
                alt="Open Paws"
                className="h-10 w-auto"
              />
              <div>
                <h1 className="text-base font-semibold text-foreground tracking-tight">Open Paws TrendFinder</h1>
              </div>
            </div>
            <div className="flex items-center gap-3">
              {authUser?.email && (
                <span className="text-xs text-muted-foreground hidden sm:block">{authUser.email}</span>
              )}
              <Button
                variant="ghost"
                size="sm"
                onClick={handleLogout}
                className="gap-1.5 h-8 text-muted-foreground"
                title="Sign out"
              >
                <LogOut className="w-3.5 h-3.5" />
                <span className="hidden sm:inline">Sign out</span>
              </Button>
            </div>
          </div>

          {/* Tabs */}
          <nav className="flex gap-0 -mb-px">
            {tabs.map(t => (
              <button
                key={t.id}
                onClick={() => setCurrentView(t.id)}
                className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-all duration-150 ${currentView === t.id
                    ? 'border-primary text-primary'
                    : 'border-transparent text-muted-foreground hover:text-foreground'
                  }`}
              >
                {t.label}
              </button>
            ))}
          </nav>
        </div>
      </header>

      {/* ── Toolbar ── */}
      {currentView === 'trends' && (
        <div className="border-b border-border bg-background">
          <div className="max-w-6xl mx-auto px-6 py-2.5 flex items-center gap-2.5 flex-wrap">
            <label htmlFor="status-filter" className="text-xs text-muted-foreground font-medium">Status</label>
            <select
              id="status-filter"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="text-xs h-8 px-2.5 rounded-lg border border-border bg-secondary text-foreground focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary transition-all font-sans cursor-pointer"
            >
              <option value="pending_review">Pending Review</option>
              <option value="explainer_ready">Explainer Ready</option>
              <option value="">All</option>
            </select>

            <Button
              id="refresh-btn"
              variant="outline"
              size="sm"
              onClick={loadTrends}
              disabled={loading || pipelineLoading}
              className="gap-1.5 h-8"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
              Refresh
            </Button>

            <Button
              variant="outline"
              size="sm"
              onClick={handleTriggerPipeline}
              disabled={loading || pipelineLoading}
              title="Manually trigger ingestion and discovery pipeline"
              className="gap-1.5 h-8 text-primary border-primary/30 hover:bg-primary/5"
            >
              <Play className="w-3.5 h-3.5" />
              {pipelineLoading ? 'Running…' : 'Run Pipeline'}
            </Button>

            {!loading && !error && (
              <span className="ml-auto text-xs text-muted-foreground">
                {count} trend{count !== 1 ? 's' : ''}
              </span>
            )}
          </div>
        </div>
      )}

      {currentView === 'history' && (
        <div className="border-b border-border bg-background">
          <div className="max-w-6xl mx-auto px-6 py-2.5 flex items-center gap-2.5">
            <Button
              id="refresh-btn"
              variant="outline"
              size="sm"
              onClick={loadHistory}
              className="gap-1.5 h-8"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              Refresh History
            </Button>
            {!loading && !error && (
              <span className="ml-auto text-xs text-muted-foreground">
                {count} record{count !== 1 ? 's' : ''}
              </span>
            )}
          </div>
        </div>
      )}

      {/* ── Main ── */}
      <main className="flex-1 max-w-6xl mx-auto w-full px-6 py-8">

        <AnimatePresence>
          {showDiscordBanner && (
            <motion.div
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              className="mb-6 relative overflow-hidden rounded-xl bg-indigo-600 px-6 py-4 flex items-center justify-between text-white shadow-md shadow-indigo-500/20"
            >
              <div className="flex items-center gap-4 relative z-10">
                <div className="bg-white/20 p-2 rounded-lg backdrop-blur-sm">
                  <Bot className="w-6 h-6 text-white" />
                </div>
                <div>
                  <h3 className="font-semibold text-white">Bring OpenPaws to your Discord Server!</h3>
                  <p className="text-sm text-indigo-100">Review trends and generate content directly from your Discord channels with our official bot.</p>
                </div>
              </div>
              <div className="flex items-center gap-3 relative z-10">
                <Button
                  variant="secondary"
                  size="sm"
                  className="bg-white text-indigo-600 hover:bg-indigo-50"
                  onClick={() => window.open('https://discord.com/api/oauth2/authorize?client_id=1509419627489263696&permissions=274877959168&scope=bot', '_blank')}
                >
                  Invite Bot
                </Button>
                <button
                  onClick={() => setShowDiscordBanner(false)}
                  className="p-1.5 hover:bg-white/10 rounded-full transition-colors text-indigo-100 hover:text-white"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
              {/* Decorative background elements */}
              <div className="absolute right-0 top-0 w-64 h-64 bg-white/5 rounded-full blur-3xl -translate-y-1/2 translate-x-1/3" />
              <div className="absolute left-1/2 bottom-0 w-32 h-32 bg-black/5 rounded-full blur-2xl translate-y-1/2" />
            </motion.div>
          )}
        </AnimatePresence>

        <AnimatePresence mode="wait">
          {loading && (
            <motion.div
              key="loader"
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              transition={{ duration: 0.3, ease: "easeOut" }}
              className="flex flex-col items-center justify-center py-32 gap-6"
            >
              <div className="relative flex items-center justify-center w-20 h-20">
                <motion.div
                  animate={{ rotate: 360 }}
                  transition={{ repeat: Infinity, duration: 2, ease: "linear" }}
                  className="absolute inset-0 rounded-full border-4 border-emerald-500/20 border-t-emerald-500 shadow-[0_0_20px_rgba(16,185,129,0.3)]"
                />
                <Sparkles className="w-8 h-8 text-emerald-500 animate-pulse" />
              </div>
              <div className="flex flex-col items-center gap-2">
                <motion.p
                  animate={{ opacity: [0.5, 1, 0.5] }}
                  transition={{ repeat: Infinity, duration: 1.5, ease: "easeInOut" }}
                  className="text-sm font-semibold tracking-wider text-emerald-600 uppercase"
                >
                  Syncing Data…
                </motion.p>
                <p className="text-xs text-muted-foreground">
                  Fetching the latest trend clusters from the database.
                </p>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        <AnimatePresence>
          {pipelineLoading && !loading && (
            <motion.div
              initial={{ opacity: 0, y: -20, height: 0 }}
              animate={{ opacity: 1, y: 0, height: 'auto' }}
              exit={{ opacity: 0, y: -20, height: 0 }}
              className="mb-6 overflow-hidden rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-4 flex items-center gap-4"
            >
              <div className="relative flex items-center justify-center w-10 h-10 shrink-0">
                <motion.div
                  animate={{ rotate: 360 }}
                  transition={{ repeat: Infinity, duration: 2, ease: "linear" }}
                  className="absolute inset-0 rounded-full border-2 border-emerald-500/20 border-t-emerald-500"
                />
                <Sparkles className="w-4 h-4 text-emerald-500 animate-pulse" />
              </div>
              <div className="flex flex-col gap-0.5">
                <p className="text-sm font-semibold text-emerald-700">Executing AI Pipeline in background…</p>
                <p className="text-xs text-emerald-600/80">Ingesting BlueSky data, generating vector embeddings, and clustering new trends. You can continue working!</p>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {error && !loading && (
          <div className="flex flex-col items-center justify-center py-24 gap-4">
            <AlertTriangle className="w-8 h-8 text-destructive" />
            <p className="text-sm text-destructive font-medium">Failed to load data</p>
            <code className="text-xs text-muted-foreground bg-secondary px-3 py-2 rounded-lg font-mono-data max-w-lg text-center break-all">
              {error}
            </code>
            <Button variant="outline" size="sm" onClick={currentView === 'trends' ? loadTrends : loadHistory}>
              Try again
            </Button>
          </div>
        )}

        {/* Trends */}
        {currentView === 'trends' && !loading && !error && trends.length === 0 && (
          <div className="flex flex-col items-center justify-center py-24 gap-3 text-muted-foreground">
            <TrendingUp className="w-8 h-8 opacity-30" />
            <p className="text-sm">No trends found for <strong>{statusFilter || 'all'}</strong> status.</p>
          </div>
        )}

        {currentView === 'trends' && !loading && !error && trends.length > 0 && (
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
            {trends.map((trend) => (
              <TrendCard key={trend.trend_id} trend={trend} jwtToken={authToken} />
            ))}
          </div>
        )}

        {/* History */}
        {currentView === 'history' && !loading && !error && history.length === 0 && (
          <div className="flex flex-col items-center justify-center py-24 gap-3 text-muted-foreground">
            <Heart className="w-8 h-8 opacity-30" />
            <p className="text-sm">No history yet. Generate some content first!</p>
          </div>
        )}

        {currentView === 'history' && !loading && !error && history.length > 0 && (
          <div className="flex flex-col gap-4">
            {history.map((item) => (
              <HistoryItem key={item.id} item={item} />
            ))}
          </div>
        )}

      </main>
    </div>
  )
}
