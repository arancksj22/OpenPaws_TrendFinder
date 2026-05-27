import { useState, useEffect, useCallback } from 'react'
import './App.css'

const API_BASE = '/api/v1/trends'
const HISTORY_API = '/api/v1/history'

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
    pending_review: { label: 'Pending Review', cls: 'badge badge--pending' },
    explainer_ready: { label: 'Explainer Ready', cls: 'badge badge--ready' },
  }
  const s = map[status] || { label: status ?? 'unknown', cls: 'badge badge--unknown' }
  return <span className={s.cls}>{s.label}</span>
}

// ─── ScoreBar ────────────────────────────────────────────────────────────────

function ScoreBar({ label, value, weight, isComposite }) {
  const pct = Math.max(0, Math.min(100, value * 100))
  const color = isComposite ? 'var(--accent)' : 'var(--green)'
  return (
    <div className={`score-bar ${isComposite ? 'score-bar--composite' : ''}`}>
      <div className="score-bar__info">
        <span className="score-bar__label" title={weight ? `Weight: ${weight * 100}%` : ''}>
          {label}
        </span>
        <span className="score-bar__value">{(value * 100).toFixed(1)}%</span>
      </div>
      <div className="score-bar__track">
        <div className="score-bar__fill" style={{ width: `${pct}%`, backgroundColor: color }} />
      </div>
    </div>
  )
}

// ─── DraftCard ───────────────────────────────────────────────────────────────

function DraftCard({ draft, metrics }) {
  const { tone, text, char_count, hashtags, passed_boundary_check, boundary_issues, is_recommended, scores } = draft
  
  return (
    <div className={`draft-card ${is_recommended ? 'draft-card--recommended' : ''} ${!passed_boundary_check ? 'draft-card--failed' : ''}`}>
      <div className="draft-card__header">
        <span className="draft-card__tone">{tone}</span>
        {is_recommended && <span className="badge badge--ready">★ Recommended</span>}
        {!passed_boundary_check && <span className="badge badge--pending">⚠ Boundary Failed</span>}
      </div>
      
      {!passed_boundary_check && boundary_issues?.length > 0 && (
        <div className="draft-card__issues">
          {boundary_issues.map((i, idx) => <div key={idx}>• {i}</div>)}
        </div>
      )}

      <p className="draft-card__text">{text}</p>
      
      <div className="draft-card__meta">
        <span>{char_count}/300 chars</span>
        {hashtags?.length > 0 && <span>· {hashtags.map(h => `#${h}`).join(' ')}</span>}
      </div>

      <div className="draft-card__scores">
        <ScoreBar label="Composite Score" value={scores.composite} isComposite={true} />
        <details className="draft-card__scores-details">
          <summary>View individual metrics</summary>
          <div className="draft-card__metrics-grid">
            {metrics.map(m => (
              <ScoreBar key={m.key} label={m.label} value={scores[m.key]} weight={m.weight} />
            ))}
          </div>
        </details>
      </div>
    </div>
  )
}

// ─── GenerationResultPanel ───────────────────────────────────────────────────

function GenerationResultPanel({ data }) {
  if (!data || !data.generation) return null
  const gen = data.generation
  const storage = data.storage

  return (
    <div className="gen-panel">
      <h4 className="gen-panel__title">✦ Generated Content</h4>
      
      <div className="gen-panel__brief">
        <h5>Advocacy Brief</h5>
        <p>{gen.advocacy_brief || (gen.scored_drafts ? 'See drafts below.' : 'No brief provided.')}</p>
      </div>

      {storage?.image_url && (
        <div className="gen-panel__image">
          <img src={storage.image_url} alt="Generated infographic" loading="lazy" />
        </div>
      )}

      <div className="gen-panel__drafts">
        <h5>Scored Drafts</h5>
        {gen.scored_drafts?.map(draft => (
          <DraftCard key={draft.index} draft={draft} metrics={gen.score_meta.metrics} />
        ))}
      </div>
    </div>
  )
}

// ─── ExplainerPanel ──────────────────────────────────────────────────────────

function ExplainerPanel({ data }) {
  if (!data) return null
  return (
    <div className="explainer-panel">
      <h4 className="explainer-panel__title">✦ AI Explainer</h4>
      <p className="explainer-panel__text">{data.explainer}</p>
      <div className="explainer-panel__meta">
        <span>Model: <code>{data.model_used}</code></span>
        <span>Prompt tokens: <code>{data.prompt_tokens ?? '—'}</code></span>
        <span>Completion tokens: <code>{data.completion_tokens ?? '—'}</code></span>
        <span>Trend ID: <code>{data.trend_id}</code></span>
      </div>
      <details className="explainer-panel__raw">
        <summary>Raw JSON</summary>
        <pre>{JSON.stringify(data, null, 2)}</pre>
      </details>
    </div>
  )
}

// ─── TrendCard ───────────────────────────────────────────────────────────────

function TrendCard({ trend, jwtToken }) {
  const [loading, setLoading] = useState(false)
  const [genLoading, setGenLoading] = useState(false)
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

  const examplePosts = trend.example_posts?.slice(0, 5) ?? []

  return (
    <article className="trend-card" id={`trend-${trend.trend_id}`}>
      <header className="trend-card__header">
        <div className="trend-card__title-row">
          <span className="trend-card__id" title={trend.trend_id}>
            #{shortId(trend.trend_id)}
          </span>
          {statusBadge(trend.status)}
        </div>
        <div className="trend-card__meta">
          <span>{trend.representative_count ?? 0} posts</span>
          <span>·</span>
          <span>Cluster: <code>{shortId(trend.cluster_key)}</code></span>
          <span>·</span>
          <span>{trend.created_at ? new Date(trend.created_at).toLocaleDateString() : '—'}</span>
        </div>
      </header>

      {examplePosts.length > 0 && (
        <section className="trend-card__posts">
          <h3 className="trend-card__section-label">Top example posts</h3>
          <ol className="posts-list">
            {examplePosts.map((post) => {
              const link = postLink(post)
              const label = post.title || post.text || post.body || post.id
              return (
                <li key={post.id} className="posts-list__item">
                  <span className="posts-list__community">{post.community}</span>
                  {link ? (
                    <a
                      className="posts-list__link"
                      href={link}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      {label}
                    </a>
                  ) : (
                    <span className="posts-list__link posts-list__link--no-href">{label}</span>
                  )}
                  <span className="posts-list__score">↑{post.score ?? 0}</span>
                </li>
              )
            })}
          </ol>
        </section>
      )}

      <footer className="trend-card__footer">
        <button
          className="btn-explain"
          onClick={handleExplain}
          disabled={loading || genLoading}
        >
          {loading ? <span className="spinner" aria-label="Loading" /> : '✦ Explain'}
        </button>
        <button
          className="btn-generate"
          onClick={handleGenerate}
          disabled={loading || genLoading}
          title="Run Phase 7-10 Pipeline"
        >
          {genLoading ? <span className="spinner" aria-label="Generating" /> : '✦ Generate'}
        </button>
        {error && <p className="trend-card__error">⚠ {error}</p>}
      </footer>

      <ExplainerPanel data={explainer} />
      <GenerationResultPanel data={generation} />
    </article>
  )
}

// ─── HistoryItem ─────────────────────────────────────────────────────────────

function HistoryItem({ item }) {
  // Format the DB record to look like the generation API response so we can reuse GenerationResultPanel
  const mockData = {
    generation: {
      advocacy_brief: item.advocacy_brief,
      score_meta: {
        // Mocking score meta since it's not stored in the DB directly, or we can just reconstruct it
        metrics: [
          { key: "advocacy_preference", label: "Advocacy Preference" },
          { key: "text_performance", label: "Text Performance" },
          { key: "potential_influence", label: "Potential Influence" },
          { key: "emotional_impact", label: "Emotional Impact" },
          { key: "animal_alignment", label: "Animal Alignment" },
        ]
      },
      scored_drafts: item.scored_drafts,
    },
    storage: {
      image_url: item.image_url
    }
  }

  return (
    <article className="trend-card history-item">
      <header className="trend-card__header">
        <div className="trend-card__title-row">
          <span className="trend-card__id">Trend #{shortId(item.trend_id)}</span>
          <span className="badge badge--ready">Generated {new Date(item.created_at).toLocaleDateString()}</span>
        </div>
      </header>
      <GenerationResultPanel data={mockData} />
    </article>
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
  const [jwtToken, setJwtToken] = useState(localStorage.getItem('openpaws_jwt') || '')
  const [currentView, setCurrentView] = useState('trends') // 'trends' or 'history'

  useEffect(() => {
    localStorage.setItem('openpaws_jwt', jwtToken)
  }, [jwtToken])

  const getHeaders = useCallback(() => {
    const h = {}
    if (jwtToken) h['Authorization'] = `Bearer ${jwtToken}`
    return h
  }, [jwtToken])

  const loadTrends = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams({ limit: 20, offset: 0 })
      if (statusFilter) params.set('status', statusFilter)
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
      const res = await fetch(`${HISTORY_API}?limit=20`, { headers: getHeaders() })
      if (!res.ok) {
        if (res.status === 401) throw new Error('Unauthorized. Please provide a valid JWT.')
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
      // Step 1: Ingest (BlueSky -> Redis)
      const trigRes = await fetch('/api/v1/pipeline/trigger', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...getHeaders() },
        body: JSON.stringify({ trigger: 'ui', async_run: false })
      })
      if (!trigRes.ok) throw new Error(`Trigger failed: ${trigRes.statusText}`)
      
      // Step 2: Discover (Redis -> Supabase trends)
      const discRes = await fetch('/api/v1/pipeline/discover', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...getHeaders() },
        body: JSON.stringify({ drain: true })
      })
      if (!discRes.ok) throw new Error(`Discovery failed: ${discRes.statusText}`)
      
      // Refresh the view
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

  return (
    <div className="app">
      {/* ── Header ── */}
      <header className="app-header">
        <div className="app-header__inner">
          <div className="app-header__top-row">
            <div className="app-header__brand">
              <span className="app-header__paw">🐾</span>
              <h1 className="app-header__title">OpenPaws TrendFinder</h1>
            </div>
            <div className="app-header__auth">
              <input 
                type="password" 
                placeholder="Paste Supabase JWT here" 
                value={jwtToken}
                onChange={e => setJwtToken(e.target.value)}
                title="Supabase Auth Token for RLS"
              />
            </div>
          </div>
          <p className="app-header__subtitle">Phase 6-10 · Human-in-the-Loop Pipeline</p>
          
          <div className="app-tabs">
            <button className={`tab-btn ${currentView === 'trends' ? 'active' : ''}`} onClick={() => setCurrentView('trends')}>Trends</button>
            <button className={`tab-btn ${currentView === 'history' ? 'active' : ''}`} onClick={() => setCurrentView('history')}>My History</button>
          </div>
        </div>
      </header>

      {/* ── Toolbar ── */}
      {currentView === 'trends' && (
        <div className="toolbar">
          <label htmlFor="status-filter" className="toolbar__label">Filter by status</label>
          <select
            id="status-filter"
            className="toolbar__select"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
          >
            <option value="pending_review">Pending Review</option>
            <option value="explainer_ready">Explainer Ready</option>
            <option value="">All</option>
          </select>
          <button id="refresh-btn" className="toolbar__refresh" onClick={loadTrends} disabled={loading || pipelineLoading}>
            ↺ Refresh
          </button>
          <button 
            className="toolbar__refresh" 
            onClick={handleTriggerPipeline} 
            disabled={loading || pipelineLoading}
            title="Manually trigger ingestion and discovery pipeline"
            style={{ color: 'var(--green)', borderColor: 'var(--green)' }}
          >
            {pipelineLoading ? 'Running...' : '▶ Run Pipeline'}
          </button>
          {!loading && !error && (
            <span className="toolbar__count">{count} trend{count !== 1 ? 's' : ''}</span>
          )}
        </div>
      )}
      
      {currentView === 'history' && (
        <div className="toolbar">
          <button id="refresh-btn" className="toolbar__refresh" onClick={loadHistory}>
            ↺ Refresh History
          </button>
          {!loading && !error && (
            <span className="toolbar__count">{count} record{count !== 1 ? 's' : ''}</span>
          )}
        </div>
      )}

      {/* ── Main content ── */}
      <main className="app-main">
        {loading && (
          <div className="state-box">
            <span className="spinner spinner--lg" aria-label="Loading" />
            <p>Loading…</p>
          </div>
        )}

        {error && !loading && (
          <div className="state-box state-box--error">
            <p>⚠ Failed to load data</p>
            <code>{error}</code>
            <button className="btn-explain" onClick={currentView === 'trends' ? loadTrends : loadHistory}>Retry</button>
          </div>
        )}

        {/* Trends View */}
        {currentView === 'trends' && !loading && !error && trends.length === 0 && (
          <div className="state-box">
            <p>No trends found for <strong>{statusFilter || 'all'}</strong> status.</p>
          </div>
        )}

        {currentView === 'trends' && !loading && !error && trends.length > 0 && (
          <div className="trends-grid">
            {trends.map((trend) => (
              <TrendCard key={trend.trend_id} trend={trend} jwtToken={jwtToken} />
            ))}
          </div>
        )}

        {/* History View */}
        {currentView === 'history' && !loading && !error && history.length === 0 && (
          <div className="state-box">
            <p>No history found for your user. Generate some content first!</p>
          </div>
        )}

        {currentView === 'history' && !loading && !error && history.length > 0 && (
          <div className="history-grid">
            {history.map((item) => (
              <HistoryItem key={item.id} item={item} />
            ))}
          </div>
        )}
      </main>
    </div>
  )
}
