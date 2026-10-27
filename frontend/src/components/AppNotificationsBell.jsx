import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import api from '../services/api'

function formatDate(iso) {
  if (!iso) return ''
  try {
    return new Date(iso).toLocaleString('fr-FR', {
      day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
    })
  } catch {
    return ''
  }
}

const SOURCE_META = {
  notes: { label: 'Notes', icon: 'bi-pencil-square', color: '#1565C0' },
  rapports: { label: 'Rapports', icon: 'bi-file-earmark-text', color: '#125a99' },
  finance: { label: 'Finance', icon: 'bi-cash-coin', color: '#F5B100' },
  presences: { label: 'Présences', icon: 'bi-calendar-x', color: '#C0392B' },
}

function normalizeItems(data, source) {
  return (data?.notifications || []).map(n => ({
    ...n,
    source,
    key: `${source}-${n.id}`,
  }))
}

export default function AppNotificationsBell({ showNotes, showRapports, showFinance, showPresences }) {
  const [open, setOpen] = useState(false)
  const [items, setItems] = useState([])
  const [nonLues, setNonLues] = useState(0)
  const [loading, setLoading] = useState(false)
  const panelRef = useRef(null)

  const fetchNotifications = useCallback(async () => {
    setLoading(true)
    const requests = []
    if (showNotes) {
      requests.push(
        api.get('/formations/notes/notifications/')
          .then(r => normalizeItems(r.data, 'notes'))
          .catch(() => []),
      )
    }
    if (showRapports) {
      requests.push(
        api.get('/statistiques/rapports/notifications/')
          .then(r => normalizeItems(r.data, 'rapports'))
          .catch(() => []),
      )
    }
    if (showFinance) {
      requests.push(
        api.get('/formations/finance/notifications/')
          .then(r => normalizeItems(r.data, 'finance'))
          .catch(() => []),
      )
    }
    if (showPresences) {
      // Alerte d'absence LMD née à la clôture de séance (ou agrégat manuel).
      requests.push(
        api.get('/stats/notifications/recues/')
          .then(r => normalizeItems(r.data, 'presences'))
          .catch(() => []),
      )
    }

    try {
      const groups = await Promise.all(requests)
      const merged = groups.flat().sort(
        (a, b) => new Date(b.created_at) - new Date(a.created_at),
      )
      setItems(merged.slice(0, 50))
      setNonLues(merged.filter(n => !n.lu).length)
    } finally {
      setLoading(false)
    }
  }, [showNotes, showRapports, showFinance, showPresences])

  useEffect(() => {
    fetchNotifications()
    const timer = setInterval(fetchNotifications, 60000)
    return () => clearInterval(timer)
  }, [fetchNotifications])

  useEffect(() => {
    if (!open) return undefined
    const onDocClick = (e) => {
      if (panelRef.current && !panelRef.current.contains(e.target)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', onDocClick)
    return () => document.removeEventListener('mousedown', onDocClick)
  }, [open])

  const patchEndpoint = (source) => {
    if (source === 'rapports') return '/statistiques/rapports/notifications/'
    if (source === 'finance') return '/formations/finance/notifications/'
    if (source === 'presences') return '/stats/notifications/recues/'
    return '/formations/notes/notifications/'
  }

  const markRead = async (item) => {
    if (item.lu) return
    try {
      await api.patch(patchEndpoint(item.source), { ids: [item.id] })
      setItems(prev => prev.map(n => (n.key === item.key ? { ...n, lu: true } : n)))
      setNonLues(c => Math.max(0, c - 1))
    } catch { /* ignore */ }
  }

  const markAllRead = async () => {
    const bySource = { notes: [], rapports: [], finance: [], presences: [] }
    items.filter(n => !n.lu).forEach(n => {
      if (bySource[n.source]) bySource[n.source].push(n.id)
    })
    try {
      await Promise.all(
        Object.entries(bySource)
          .filter(([, ids]) => ids.length > 0)
          .map(([source]) => api.patch(patchEndpoint(source), { tout: true })),
      )
      setItems(prev => prev.map(n => ({ ...n, lu: true })))
      setNonLues(0)
    } catch { /* ignore */ }
  }

  const itemLink = (item) => {
    if (item.source === 'finance') return '/finance-ajustements'
    if (item.source === 'rapports') return '/statistiques?rbView=workflow'
    return null
  }

  if (!showNotes && !showRapports && !showFinance && !showPresences) return null

  return (
    <div ref={panelRef} style={{ position: 'relative' }}>
      <button
        type="button"
        className="btn btn-sm btn-outline-secondary"
        title="Notifications"
        onClick={() => { setOpen(o => !o); if (!open) fetchNotifications() }}
        style={{ position: 'relative' }}
      >
        <i className="bi bi-bell" />
        {nonLues > 0 && (
          <span style={{
            position: 'absolute', top: -4, right: -4,
            background: '#c62828', color: '#fff', borderRadius: '999px',
            fontSize: '0.65rem', fontWeight: 700, minWidth: 16, height: 16,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            padding: '0 4px',
          }}>
            {nonLues > 9 ? '9+' : nonLues}
          </span>
        )}
      </button>

      {open && (
        <div style={{
          position: 'absolute', right: 0, top: 'calc(100% + 0.35rem)', width: 380,
          maxHeight: 440, overflowY: 'auto', background: '#fff',
          border: '1px solid var(--border, #e2e8f0)', borderRadius: 10,
          boxShadow: '0 8px 24px rgba(0,0,0,0.12)', zIndex: 1000,
        }}>
          <div style={{
            padding: '0.65rem 0.85rem', borderBottom: '1px solid #e2e8f0',
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            background: '#f8fafc',
          }}>
            <strong style={{ fontSize: '0.85rem' }}>Notifications</strong>
            {nonLues > 0 && (
              <button type="button" className="btn btn-link btn-sm p-0" onClick={markAllRead}>
                Tout marquer lu
              </button>
            )}
          </div>

          {loading && items.length === 0 ? (
            <div style={{ padding: '1rem', color: '#64748b', fontSize: '0.85rem' }}>Chargement…</div>
          ) : items.length === 0 ? (
            <div style={{ padding: '1rem', color: '#64748b', fontSize: '0.85rem' }}>
              Aucune notification.
            </div>
          ) : (
            items.map(n => {
              const meta = SOURCE_META[n.source] || SOURCE_META.notes
              const href = itemLink(n)
              const inner = (
                <>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', marginBottom: '0.25rem' }}>
                    <span style={{
                      fontSize: '0.65rem', fontWeight: 700, textTransform: 'uppercase',
                      color: meta.color, letterSpacing: '0.03em',
                    }}>
                      <i className={`bi ${meta.icon} me-1`} />
                      {meta.label}
                    </span>
                  </div>
                  <div style={{ fontSize: '0.82rem', lineHeight: 1.45, color: '#1e293b' }}>
                    {n.message}
                  </div>
                  <div style={{ fontSize: '0.72rem', color: '#94a3b8', marginTop: '0.25rem' }}>
                    {formatDate(n.created_at)}
                  </div>
                </>
              )
              const style = {
                display: 'block', width: '100%', textAlign: 'left', border: 'none',
                borderBottom: '1px solid #f1f5f9', cursor: 'pointer',
                padding: '0.65rem 0.85rem', background: n.lu ? '#fff' : '#fffae1',
                textDecoration: 'none', color: 'inherit',
              }
              if (href) {
                return (
                  <Link
                    key={n.key}
                    to={href}
                    style={style}
                    onClick={() => { if (!n.lu) markRead(n); setOpen(false) }}
                  >
                    {inner}
                  </Link>
                )
              }
              return (
                <button
                  key={n.key}
                  type="button"
                  style={style}
                  onClick={() => markRead(n)}
                >
                  {inner}
                </button>
              )
            })
          )}
        </div>
      )}
    </div>
  )
}
