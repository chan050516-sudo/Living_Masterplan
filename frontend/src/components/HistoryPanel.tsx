import { C, mono } from '../theme'
import type { AnalyzeHistoryItem } from '../App'

export function HistoryPanel({
  history, onClose, onUpdateStatus, onPreview, activeRunId, onSelectHistory, onClear
}: {
  history: AnalyzeHistoryItem[]
  onClose: () => void
  onUpdateStatus: (id: string, status: 'accepted' | 'declined') => void
  onPreview: (id: string) => void
  activeRunId?: string
  onSelectHistory: (item: AnalyzeHistoryItem) => void
  onClear: () => void
}) {
  return (
    <div className="fade">
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20 }}>
        <h2 style={{ margin: 0, fontSize: 18, fontWeight: 500 }}>Analysis History</h2>

        {history.length > 0 && (
          <button 
            onClick={onClear}
            style={{ background: 'none', border: 'none', color: '#d71920', fontSize: 12, cursor: 'pointer', opacity: 0.8, padding: 0 }}
            onMouseOver={(e) => e.currentTarget.style.opacity = '1'}
            onMouseOut={(e) => e.currentTarget.style.opacity = '0.8'}
          >
            Clear All
          </button>
        )}

        <span style={{ flex: 1 }} />
        <button onClick={onClose} style={{ background: 'none', border: 0, color: C.muted, fontSize: 20, cursor: 'pointer' }}>×</button>
      </div>

      {history.length === 0 && <p style={{ color: C.faint, fontSize: 13 }}>No analyses yet. Select assets and click Ask.</p>}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        {history.map((item) => (
          <div 
            key={item.id} 
            onClick={() => onSelectHistory(item)}
            style={{ 
              padding: 16, 
              background: C.card, 
              border: `1px solid ${activeRunId === item.id ? '#00d2ff' : C.line}`, 
              borderRadius: 8,
              cursor: 'pointer',
              transition: 'border-color 0.2s',
            }}
            className="hover-card"
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
              <span style={{ ...mono, fontSize: 11, color: C.faint }}>{item.id}</span>
              <span style={{ 
                fontSize: 11, fontWeight: 600, 
                color: item.status === 'accepted' ? '#3fb27f' : item.status === 'declined' ? '#d71920' : '#f7931d' 
              }}>
                {item.status.toUpperCase()}
              </span>
            </div>
            
            <strong style={{ display: 'block', fontSize: 14, color: '#fff', marginBottom: 8 }}>{item.result.decision.selected_candidate}</strong>
            <p style={{ margin: '0 0 14px 0', fontSize: 12, color: C.muted, lineHeight: 1.5 }}>
              {item.result.decision.reasoning}
            </p>

            <div style={{ display: 'flex', gap: 8 }}>
              {item.status === 'pending' && (
                <>
                  <button 
                    className="btn" 
                    onClick={(e) => { e.stopPropagation(); onUpdateStatus(item.id, 'accepted') }}
                    style={{ flex: 1, background: '#3fb27f', color: '#fff', borderColor: '#3fb27f' }}
                  >
                    Accept
                  </button>
                  <button 
                    className="btn" 
                    onClick={(e) => { e.stopPropagation(); onUpdateStatus(item.id, 'declined') }}
                    style={{ flex: 1, background: 'transparent', color: '#d71920', borderColor: '#d71920' }}
                  >
                    Decline
                  </button>
                </>
              )}
              {item.status === 'accepted' && (
                <button 
                  className="btn primary" 
                  onClick={(e) => { e.stopPropagation(); onPreview(item.id) }}
                  style={{ flex: 1, background: '#00d2ff', color: '#000', border: 'none' }}
                >
                  Show on Map
                </button>
              )}
              {item.status === 'declined' && (
                <button 
                  className="btn" 
                  disabled
                  style={{ flex: 1, opacity: 0.5, cursor: 'not-allowed' }}
                >
                  Declined
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}