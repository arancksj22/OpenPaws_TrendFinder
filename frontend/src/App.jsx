import { useState, useEffect, useCallback } from 'react'
import './App.css'

const API_BASE = '/api/v1/trends'

// ─── helpers ─────────────────────────────────────────────────────────────────

function postLink(post) {
  if (post.permalink) return `https://reddit.com${post.permalink}`
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

function TrendCard({ trend }) {
  const [loading, setLoading] = useState(false)
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
  const [error, setError] = useState(null)

  const handleExplain = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`${API_BASE}/${trend.trend_id}/explainer`, {
        method: 'POST',
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
  }, [trend.trend_id])

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
                  <span className="posts-list__community">r/{post.community}</span>
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
          id={`explain-btn-${trend.trend_id}`}
          className="btn-explain"
          onClick={handleExplain}
          disabled={loading}
        >
          {loading ? (
            <span className="spinner" aria-label="Loading" />
          ) : (
            '✦ Explain'
          )}
        </button>
        {error && <p className="trend-card__error">⚠ {error}</p>}
      </footer>

      <ExplainerPanel data={explainer} />
    </article>
  )
}

// ─── App ─────────────────────────────────────────────────────────────────────

export default function App() {
  const [trends, setTrends] = useState([])
  const [count, setCount] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [statusFilter, setStatusFilter] = useState('pending_review')

  const loadTrends = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams({ limit: 20, offset: 0 })
      if (statusFilter) params.set('status', statusFilter)
      const res = await fetch(`${API_BASE}/?${params}`)
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
      const data = await res.json()
      setTrends(data.trends ?? [])
      setCount(data.count ?? 0)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [statusFilter])

  useEffect(() => {
    loadTrends()
  }, [loadTrends])

  return (
    <div className="app">
      {/* ── Header ── */}
      <header className="app-header">
        <div className="app-header__inner">
          <div className="app-header__brand">
            <span className="app-header__paw">🐾</span>
            <h1 className="app-header__title">OpenPaws TrendFinder</h1>
          </div>
          <p className="app-header__subtitle">Phase 6 · Human-in-the-Loop Trend Explainer</p>
        </div>
      </header>

      {/* ── Toolbar ── */}
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
        <button id="refresh-btn" className="toolbar__refresh" onClick={loadTrends}>
          ↺ Refresh
        </button>
        {!loading && !error && (
          <span className="toolbar__count">{count} trend{count !== 1 ? 's' : ''}</span>
        )}
      </div>

      {/* ── Main content ── */}
      <main className="app-main">
        {loading && (
          <div className="state-box">
            <span className="spinner spinner--lg" aria-label="Loading trends" />
            <p>Loading trends…</p>
          </div>
        )}

        {error && !loading && (
          <div className="state-box state-box--error">
            <p>⚠ Failed to load trends</p>
            <code>{error}</code>
            <button className="btn-explain" onClick={loadTrends}>Retry</button>
          </div>
        )}

        {!loading && !error && trends.length === 0 && (
          <div className="state-box">
            <p>No trends found for <strong>{statusFilter || 'all'}</strong> status.</p>
          </div>
        )}

        {!loading && !error && trends.length > 0 && (
          <div className="trends-grid">
            {trends.map((trend) => (
              <TrendCard key={trend.trend_id} trend={trend} />
            ))}
          </div>
        )}
      </main>
    </div>
  )
}
