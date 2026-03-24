import { useState } from 'react'
import {
  usePipelineRuns, useHealingStats, useHealingLog, usePipelineStats,
  useDeliveryLog, useEvals, useConversationLog, useDeliveryMetricsAgg,
} from '../api/hooks'
import { MetricCard } from '../components/MetricCard'
import { PageLoader } from '../components/LoadingSpinner'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const STATUS_COLOR: Record<string, string> = {
  ok: '#2a9d8f', success: '#2a9d8f', completed: '#2a9d8f',
  partial: '#f4a261', running: '#1976D2',
  failed: '#e63946', error: '#e63946',
}

const DELIVERY_STATUS_COLOR: Record<string, string> = {
  sent: '#2a9d8f', dry_run: '#2a9d8f', failed: '#e63946',
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatTime(dateStr: string | undefined): string {
  if (!dateStr) return '--'
  try {
    return new Date(dateStr).toLocaleString('en-IN', { dateStyle: 'short', timeStyle: 'short' })
  } catch { return dateStr }
}

// ---------------------------------------------------------------------------
// Visual Architecture Diagram
// ---------------------------------------------------------------------------

const DATA_SOURCES = [
  { emoji: '\uD83D\uDD27', name: 'IMD / imdlib', desc: 'Station observations', feeds: 'Step 1', color: '#2E7D32' },
  { emoji: '\uD83C\uDF10', name: 'Tomorrow.io', desc: 'Cross-validation ref', feeds: 'Step 2', color: '#1565C0' },
  { emoji: '\uD83D\uDCE1', name: 'NeuralGCM / Open-Meteo', desc: 'NWP forecasts', feeds: 'Step 3', color: '#7B1FA2' },
  { emoji: '\uD83D\uDEF0\uFE0F', name: 'NASA POWER', desc: 'Spatial grid (0.5\u00B0)', feeds: 'Steps 2, 4', color: '#E65100' },
  { emoji: '\uD83E\uDD16', name: 'Claude API', desc: 'Advisory + Translation', feeds: 'Step 5', color: '#C62828' },
]

const PIPELINE_STEPS = [
  { num: 1, name: 'Ingest', table: 'raw_telemetry', desc: 'IMD station data', color: '#2E7D32' },
  { num: 2, name: 'Heal', table: 'clean_telemetry', desc: 'Anomaly detection\n+ imputation', color: '#1565C0' },
  { num: 3, name: 'Forecast', table: 'forecasts', desc: 'MOS: NWP +\nXGBoost residual', color: '#7B1FA2' },
  { num: 4, name: 'Downscale', table: 'forecasts', desc: 'IDW + lapse-rate\n\u2192 farmer GPS', color: '#E65100' },
  { num: 5, name: 'Translate', table: 'agricultural_alerts', desc: 'RAG + Claude\nadvisory', color: '#C62828' },
  { num: 6, name: 'Deliver', table: 'delivery_log', desc: 'SMS + WhatsApp', color: '#d4a019' },
]

const DEGRADATION_CHAIN = [
  { trigger: 'NeuralGCM unavailable', fallback: 'Open-Meteo API fallback' },
  { trigger: 'Open-Meteo unavailable', fallback: 'Persistence model (last obs + diurnal)' },
  { trigger: 'Claude healing down', fallback: 'Rule-based fallback' },
  { trigger: 'Claude advisory down', fallback: 'Template advisories' },
  { trigger: 'Tomorrow.io down', fallback: 'NASA POWER cross-validation' },
  { trigger: 'Translation fails', fallback: 'English advisory only' },
]

function ArchitectureDiagram() {
  return (
    <div className="space-y-6">
      {/* Data Sources */}
      <div>
        <div style={{
          fontSize: '0.72rem', fontWeight: 600, textTransform: 'uppercase' as const,
          letterSpacing: '1.5px', color: '#888', marginBottom: '10px',
        }}>
          Data Sources (each API has ONE job)
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
          {DATA_SOURCES.map(s => (
            <div key={s.name} style={{
              background: '#fff', border: '1px solid #e0dcd5', borderRadius: '8px',
              borderLeft: `4px solid ${s.color}`, padding: '12px 14px',
            }}>
              <div style={{ fontSize: '1.2rem', marginBottom: '4px' }}>{s.emoji}</div>
              <div style={{ fontWeight: 600, fontSize: '0.82rem', color: '#1a1a1a' }}>{s.name}</div>
              <div style={{ fontSize: '0.75rem', color: '#888', marginTop: '2px' }}>{s.desc}</div>
              <div style={{
                fontSize: '0.68rem', color: s.color, fontWeight: 600,
                marginTop: '6px', textTransform: 'uppercase' as const, letterSpacing: '0.5px',
              }}>
                \u2192 {s.feeds}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Vertical flow indicator */}
      <div style={{ textAlign: 'center', color: '#d4a019', fontSize: '1.5rem', lineHeight: 1 }}>
        \u25BC \u25BC \u25BC
      </div>

      {/* Pipeline Steps */}
      <div>
        <div style={{
          fontSize: '0.72rem', fontWeight: 600, textTransform: 'uppercase' as const,
          letterSpacing: '1.5px', color: '#888', marginBottom: '10px',
        }}>
          Pipeline (6 steps, linear)
        </div>
        <div style={{
          display: 'flex', gap: '0', overflowX: 'auto',
          WebkitOverflowScrolling: 'touch', paddingBottom: '4px',
        }}>
          {PIPELINE_STEPS.map((s, i) => (
            <div key={s.num} style={{ display: 'flex', alignItems: 'stretch', flexShrink: 0 }}>
              <div style={{
                background: s.color, color: '#fff', borderRadius: '8px',
                padding: '14px 16px', minWidth: '130px', position: 'relative',
              }}>
                <div style={{ fontSize: '0.68rem', opacity: 0.8, fontWeight: 600 }}>
                  Step {s.num}
                </div>
                <div style={{ fontSize: '0.95rem', fontWeight: 700, marginTop: '2px' }}>
                  {s.name}
                </div>
                <div style={{ fontSize: '0.72rem', opacity: 0.85, marginTop: '4px', whiteSpace: 'pre-line' }}>
                  {s.desc}
                </div>
                <div style={{
                  fontSize: '0.65rem', opacity: 0.7, marginTop: '6px',
                  fontFamily: 'monospace', background: 'rgba(255,255,255,0.15)',
                  padding: '2px 6px', borderRadius: '3px', display: 'inline-block',
                }}>
                  {s.table}
                </div>
              </div>
              {i < PIPELINE_STEPS.length - 1 && (
                <div style={{
                  display: 'flex', alignItems: 'center', padding: '0 6px',
                  color: '#d4a019', fontSize: '1.2rem', fontWeight: 700, flexShrink: 0,
                }}>
                  \u2192
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Degradation Chain */}
      <div>
        <div style={{
          fontSize: '0.72rem', fontWeight: 600, textTransform: 'uppercase' as const,
          letterSpacing: '1.5px', color: '#888', marginBottom: '10px',
        }}>
          Degradation Chain (independent, never cascades)
        </div>
        <div style={{
          background: '#fff', border: '1px solid #e0dcd5', borderRadius: '8px',
          overflow: 'hidden',
        }}>
          {DEGRADATION_CHAIN.map((d, i) => (
            <div key={i} style={{
              display: 'flex', alignItems: 'center', gap: '12px',
              padding: '8px 14px',
              borderBottom: i < DEGRADATION_CHAIN.length - 1 ? '1px solid #f0ede8' : 'none',
            }}>
              <span style={{
                fontSize: '0.78rem', color: '#e63946', fontWeight: 500, minWidth: '200px',
              }}>
                {d.trigger}
              </span>
              <span style={{ color: '#d4a019', fontSize: '0.9rem' }}>\u2192</span>
              <span style={{ fontSize: '0.78rem', color: '#2a9d8f', fontWeight: 500 }}>
                {d.fallback}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Eval Metrics Tab
// ---------------------------------------------------------------------------

function EvalMetricsTab() {
  const { data: evals, isLoading } = useEvals()

  if (isLoading) return <p style={{ color: '#888', fontSize: '0.85rem' }}>Loading eval data...</p>

  if (!evals || Object.keys(evals).length === 0) {
    return (
      <div className="space-y-4">
        <div className="card card-body" style={{ textAlign: 'center', padding: '32px' }}>
          <p style={{ color: '#888', fontSize: '0.9rem', marginBottom: '16px' }}>
            No eval results found yet. Run the eval scripts from the project root:
          </p>
          <pre style={{
            background: '#1a1a1a', color: '#e0dcd5', borderRadius: '8px',
            padding: '16px', fontSize: '0.78rem', textAlign: 'left',
            overflow: 'auto', lineHeight: 1.8,
          }}>
{`python tests/eval_healing.py         # Self-healing detection accuracy
python tests/eval_forecast.py        # Forecast accuracy (MAE/RMSE)
python tests/eval_rag.py             # RAG retrieval precision/recall
python tests/eval_advisory.py        # Advisory quality scoring
python tests/eval_translation.py     # Translation quality
python tests/eval_dpi.py             # DPI profile coverage & realism
python tests/eval_conversation.py    # Conversation engine quality`}
          </pre>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Healing */}
      {evals.healing && (() => {
        const h = evals.healing
        const bd = h.binary_detection || {}
        const pft = h.per_fault_type || {}
        return (
          <div className="space-y-3">
            <div className="section-header">Self-Healing Detection</div>
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
              <MetricCard label="Precision" value={bd.precision != null ? `${(bd.precision * 100).toFixed(0)}%` : '--'} />
              <MetricCard label="Recall" value={bd.recall != null ? `${(bd.recall * 100).toFixed(0)}%` : '--'} />
              <MetricCard label="F1" value={bd.f1 != null ? `${(bd.f1 * 100).toFixed(0)}%` : '--'} />
              <MetricCard label="Total Readings" value={h.total_readings ?? '--'} />
            </div>
            {Object.keys(pft).length > 0 && (
              <div className="table-container">
                <table>
                  <thead><tr><th>Fault Type</th><th>Count</th><th>Detection Rate</th><th>Imputation MAE</th></tr></thead>
                  <tbody>
                    {Object.entries(pft).map(([ft, m]: [string, any]) => (
                      <tr key={ft}>
                        <td style={{ fontWeight: 500 }}>{ft}</td>
                        <td>{m.count ?? 0}</td>
                        <td>{m.accuracy != null ? `${(m.accuracy * 100).toFixed(0)}%` : 'N/A'}</td>
                        <td>{m.imputation_mae != null ? m.imputation_mae.toFixed(2) : '---'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )
      })()}

      {/* Forecast */}
      {evals.forecast && (() => {
        const f = evals.forecast
        const temp = f.overall?.temperature || {}
        const byModel = f.by_model || {}
        return (
          <div className="space-y-3">
            <div className="section-header">Forecast Accuracy</div>
            <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
              <MetricCard label="Temp MAE" value={temp.mae != null ? `${temp.mae.toFixed(2)} C` : '---'} />
              <MetricCard label="Temp RMSE" value={temp.rmse != null ? `${temp.rmse.toFixed(2)} C` : '---'} />
              <MetricCard label="Paired Records" value={f.total_pairs ?? 0} />
            </div>
            {Object.keys(byModel).length > 0 && (
              <div className="table-container">
                <table>
                  <thead><tr><th>Model</th><th>N</th><th>MAE (C)</th><th>RMSE (C)</th><th>Bias (C)</th></tr></thead>
                  <tbody>
                    {Object.entries(byModel).map(([mt, m]: [string, any]) => (
                      <tr key={mt}>
                        <td style={{ fontWeight: 500 }}>{mt}</td>
                        <td>{m.n ?? 0}</td>
                        <td>{m.mae != null ? m.mae.toFixed(2) : '---'}</td>
                        <td>{m.rmse != null ? m.rmse.toFixed(2) : '---'}</td>
                        <td>{m.bias != null ? (m.bias >= 0 ? '+' : '') + m.bias.toFixed(2) : '---'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )
      })()}

      {/* RAG */}
      {evals.rag && (() => {
        const byMode = evals.rag.by_mode || {}
        return (
          <div className="space-y-3">
            <div className="section-header">RAG Retrieval Quality</div>
            {Object.keys(byMode).length > 0 && (
              <div className="table-container">
                <table>
                  <thead><tr><th>Mode</th><th>Avg Precision@5</th><th>Avg Recall</th><th>Cases</th></tr></thead>
                  <tbody>
                    {Object.entries(byMode).map(([mode, m]: [string, any]) => (
                      <tr key={mode}>
                        <td style={{ fontWeight: 500 }}>{mode}</td>
                        <td>{(m.avg_precision ?? 0).toFixed(2)}</td>
                        <td>{(m.avg_recall ?? 0).toFixed(2)}</td>
                        <td>{m.n_cases ?? 0}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )
      })()}

      {/* Advisory */}
      {evals.advisory && (() => {
        const byProv = evals.advisory.by_provider || {}
        return (
          <div className="space-y-3">
            <div className="section-header">Advisory Quality</div>
            {Object.keys(byProv).length > 0 && (
              <div className="table-container">
                <table>
                  <thead><tr><th>Provider</th><th>Accuracy</th><th>Actionability</th><th>Safety</th><th>Cultural</th></tr></thead>
                  <tbody>
                    {Object.entries(byProv).map(([prov, m]: [string, any]) => (
                      <tr key={prov}>
                        <td style={{ fontWeight: 500 }}>{prov}</td>
                        <td>{(m.avg_accuracy ?? 0).toFixed(1)}/5</td>
                        <td>{(m.avg_actionability ?? 0).toFixed(1)}/5</td>
                        <td>{m.avg_safety != null ? (m.avg_safety >= 0 ? '+' : '') + m.avg_safety.toFixed(1) : '--'}</td>
                        <td>{(m.avg_cultural ?? 0).toFixed(1)}/5</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )
      })()}

      {/* Translation */}
      {evals.translation && (() => {
        const t = evals.translation
        const byLang = t.by_language || {}
        return (
          <div className="space-y-3">
            <div className="section-header">Translation Quality</div>
            <div className="grid grid-cols-2 gap-4">
              <MetricCard label="Semantic Similarity" value={t.avg_similarity != null ? `${t.avg_similarity.toFixed(1)}/5` : '--'} />
              <MetricCard label="Ag Term Preservation" value={t.avg_ag_preservation != null ? `${(t.avg_ag_preservation * 100).toFixed(0)}%` : '--'} />
            </div>
            {Object.keys(byLang).length > 0 && (
              <div className="table-container">
                <table>
                  <thead><tr><th>Language</th><th>N</th><th>Similarity</th><th>Ag Preservation</th></tr></thead>
                  <tbody>
                    {Object.entries(byLang).map(([lang, m]: [string, any]) => (
                      <tr key={lang}>
                        <td style={{ fontWeight: 500 }}>{lang === 'ta' ? 'Tamil' : lang === 'ml' ? 'Malayalam' : lang}</td>
                        <td>{m.n ?? 0}</td>
                        <td>{(m.avg_similarity ?? 0).toFixed(1)}/5</td>
                        <td>{m.avg_ag_preservation != null ? `${(m.avg_ag_preservation * 100).toFixed(0)}%` : '--'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )
      })()}

      {/* DPI */}
      {evals.dpi && (() => {
        const d = evals.dpi
        return (
          <div className="space-y-3">
            <div className="section-header">DPI Profile Quality</div>
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
              <MetricCard label="Farmers" value={d.total_farmers ?? 0} />
              <MetricCard label="Station Coverage" value={d.coverage?.coverage_rate != null ? `${(d.coverage.coverage_rate * 100).toFixed(0)}%` : '--'} />
              <MetricCard label="Completeness" value={d.completeness?.completeness_rate != null ? `${(d.completeness.completeness_rate * 100).toFixed(0)}%` : '--'} />
              <MetricCard label="Consistency" value={d.consistency?.rate != null ? `${(d.consistency.rate * 100).toFixed(0)}%` : '--'} />
            </div>
          </div>
        )
      })()}

      {/* Conversation */}
      {evals.conversation && (() => {
        const c = evals.conversation
        return (
          <div className="space-y-3">
            <div className="section-header">Conversation Engine</div>
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
              <MetricCard label="State Machine" value={c.state_machine?.accuracy != null ? `${(c.state_machine.accuracy * 100).toFixed(0)}%` : '--'} />
              <MetricCard label="Language Detection" value={c.language_detection?.accuracy != null ? `${(c.language_detection.accuracy * 100).toFixed(0)}%` : '--'} />
              <MetricCard label="Escalation Detection" value={c.escalation_detection?.accuracy != null ? `${(c.escalation_detection.accuracy * 100).toFixed(0)}%` : '--'} />
              <MetricCard label="Overall" value={c.overall?.overall_rate != null ? `${(c.overall.overall_rate * 100).toFixed(0)}%` : '--'} />
            </div>
          </div>
        )
      })()}

      <p style={{ fontSize: '0.78rem', color: '#888', fontStyle: 'italic' }}>
        Run eval scripts from the project root to update these metrics.
      </p>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Agent Log Tab
// ---------------------------------------------------------------------------

function AgentLogTab() {
  const { data: convLog, isLoading } = useConversationLog(200)

  if (isLoading) return <p style={{ color: '#888', fontSize: '0.85rem' }}>Loading conversation log...</p>

  const logs = convLog ?? []

  if (logs.length === 0) {
    return (
      <div className="card card-body text-center py-8">
        <p style={{ color: '#888', fontSize: '0.85rem' }}>
          No conversation logs yet. Use the Chat widget or <code>python run_chat.py</code> to generate data.
        </p>
      </div>
    )
  }

  const userMsgs = logs.filter(l => l.role === 'user')
  const assistantMsgs = logs.filter(l => l.role === 'assistant')
  const toolUse = logs.filter(l => l.role === 'tool_use')
  const sessions = new Set(logs.map(l => l.session_id).filter(Boolean)).size

  // Tool usage counts
  const toolCounts: Record<string, number> = {}
  for (const t of toolUse) {
    const name = t.tool_name || 'unknown'
    toolCounts[name] = (toolCounts[name] || 0) + 1
  }

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard label="Sessions" value={sessions} />
        <MetricCard label="User Queries" value={userMsgs.length} />
        <MetricCard label="Responses" value={assistantMsgs.length} />
        <MetricCard label="Tool Calls" value={toolUse.length} />
      </div>

      {Object.keys(toolCounts).length > 0 && (
        <div>
          <div className="section-header">Tool Usage</div>
          <div className="table-container">
            <table>
              <thead><tr><th>Tool</th><th>Count</th></tr></thead>
              <tbody>
                {Object.entries(toolCounts).sort((a, b) => b[1] - a[1]).map(([tool, count]) => (
                  <tr key={tool}>
                    <td style={{ fontWeight: 500 }}>{tool}</td>
                    <td>{count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div>
        <div className="section-header">Recent Conversations</div>
        <div className="table-container">
          <table>
            <thead><tr><th>Session</th><th>Query</th><th>Time</th></tr></thead>
            <tbody>
              {userMsgs.slice(0, 20).map((m, i) => (
                <tr key={m.id ?? i}>
                  <td style={{ fontFamily: 'monospace', fontSize: '0.75rem', color: '#aaa' }}>
                    {(m.session_id || '').slice(0, 8)}
                  </td>
                  <td style={{ fontSize: '0.82rem', maxWidth: '400px' }} className="truncate">
                    {(m.content || '').slice(0, 100)}
                  </td>
                  <td style={{ fontSize: '0.78rem', color: '#888' }}>{formatTime(m.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Delivery Funnel Tab
// ---------------------------------------------------------------------------

function DeliveryFunnelTab() {
  const { data: metrics, isLoading } = useDeliveryMetricsAgg(500)

  if (isLoading) return <p style={{ color: '#888', fontSize: '0.85rem' }}>Loading delivery metrics...</p>

  const dm = metrics ?? []

  if (dm.length === 0) {
    return (
      <div className="card card-body text-center py-8">
        <p style={{ color: '#888', fontSize: '0.85rem' }}>
          No delivery metrics yet. Run <code>python run_pipeline.py</code> to generate data.
        </p>
      </div>
    )
  }

  const totalStations = new Set(dm.map(d => d.station_id).filter(Boolean)).size
  const totalForecasts = dm.reduce((s, d) => s + (d.forecasts_generated || 0), 0)
  const totalAdvisories = dm.reduce((s, d) => s + (d.advisories_generated || 0), 0)
  const totalAttempted = dm.reduce((s, d) => s + (d.deliveries_attempted || 0), 0)
  const totalSucceeded = dm.reduce((s, d) => s + (d.deliveries_succeeded || 0), 0)

  const funnel = [
    { label: 'Stations', value: totalStations, color: '#2E7D32' },
    { label: 'Forecasts', value: totalForecasts, color: '#1565C0' },
    { label: 'Advisories', value: totalAdvisories, color: '#d4a019' },
    { label: 'Attempted', value: totalAttempted, color: '#E65100' },
    { label: 'Succeeded', value: totalSucceeded, color: '#2a9d8f' },
  ]
  const maxVal = Math.max(...funnel.map(f => f.value), 1)

  // Per-station aggregation
  const stationAgg: Record<string, { fc: number; adv: number; att: number; succ: number }> = {}
  for (const d of dm) {
    const sid = d.station_id || 'unknown'
    if (!stationAgg[sid]) stationAgg[sid] = { fc: 0, adv: 0, att: 0, succ: 0 }
    stationAgg[sid].fc += d.forecasts_generated || 0
    stationAgg[sid].adv += d.advisories_generated || 0
    stationAgg[sid].att += d.deliveries_attempted || 0
    stationAgg[sid].succ += d.deliveries_succeeded || 0
  }

  return (
    <div className="space-y-6">
      <div className="section-header">Delivery Funnel</div>

      {/* Funnel metrics */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
        {funnel.map(f => (
          <MetricCard key={f.label} label={f.label} value={f.value} />
        ))}
      </div>

      {/* Funnel bar chart */}
      <div style={{
        background: '#fff', border: '1px solid #e0dcd5', borderRadius: '8px', padding: '16px',
      }}>
        {funnel.map(f => (
          <div key={f.label} style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '8px' }}>
            <div style={{ width: '90px', fontSize: '0.78rem', fontWeight: 500, color: '#555', textAlign: 'right' }}>
              {f.label}
            </div>
            <div style={{ flex: 1, background: '#f0ede8', borderRadius: '4px', height: '24px', overflow: 'hidden' }}>
              <div style={{
                width: `${(f.value / maxVal) * 100}%`, height: '100%',
                background: f.color, borderRadius: '4px',
                display: 'flex', alignItems: 'center', paddingLeft: '8px',
                fontSize: '0.72rem', color: '#fff', fontWeight: 600,
                minWidth: f.value > 0 ? '30px' : '0',
              }}>
                {f.value}
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Per-station breakdown */}
      <div className="section-header">Per-Station Breakdown</div>
      <div className="table-container">
        <table>
          <thead>
            <tr><th>Station</th><th>Forecasts</th><th>Advisories</th><th>Attempted</th><th>Succeeded</th><th>Success %</th></tr>
          </thead>
          <tbody>
            {Object.entries(stationAgg).sort((a, b) => a[0].localeCompare(b[0])).map(([sid, s]) => {
              const rate = s.att > 0 ? ((s.succ / s.att) * 100).toFixed(1) : '--'
              return (
                <tr key={sid}>
                  <td style={{ fontWeight: 500 }}>{sid}</td>
                  <td>{s.fc}</td>
                  <td>{s.adv}</td>
                  <td>{s.att}</td>
                  <td>{s.succ}</td>
                  <td style={{ color: rate !== '--' && parseFloat(rate) >= 90 ? '#2a9d8f' : '#e63946' }}>
                    {rate === '--' ? '--' : `${rate}%`}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Delivery Log Tab (deferred — only fetches when active)
// ---------------------------------------------------------------------------

function SystemDeliveryLogTab() {
  const deliveries = useDeliveryLog(200)
  const allDeliveries = deliveries.data ?? []
  const sentCount = allDeliveries.filter(d => d.status === 'sent' || d.status === 'dry_run').length

  if (deliveries.isLoading) return <p style={{ color: '#888', fontSize: '0.85rem' }}>Loading deliveries...</p>

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
        <MetricCard label="Sent / Dry-Run" value={sentCount} />
        <MetricCard label="Failed" value={allDeliveries.filter(d => d.status === 'failed').length} />
        <MetricCard label="Channels Used" value={new Set(allDeliveries.map(d => d.channel)).size || '--'} />
      </div>

      {allDeliveries.length === 0 ? (
        <div className="card card-body text-center py-8">
          <p style={{ color: '#888', fontSize: '0.85rem' }}>No delivery records</p>
        </div>
      ) : (
        <div className="table-container">
          <table>
            <thead>
              <tr><th>Station</th><th>Channel</th><th>Recipient</th><th>Status</th><th>Message</th><th>Time</th></tr>
            </thead>
            <tbody>
              {allDeliveries.map((d, i) => {
                const sColor = DELIVERY_STATUS_COLOR[d.status || ''] || '#888'
                return (
                  <tr key={d.id ?? i}>
                    <td>{d.station_id || '--'}</td>
                    <td>{d.channel || '--'}</td>
                    <td style={{ fontSize: '0.82rem' }}>{d.recipient || '--'}</td>
                    <td>
                      <span style={{
                        background: `${sColor}26`, color: sColor,
                        padding: '2px 8px', borderRadius: '4px',
                        fontSize: '0.78rem', fontWeight: 600,
                      }}>{d.status || '--'}</span>
                    </td>
                    <td style={{ fontSize: '0.82rem', color: '#555', maxWidth: '200px' }} className="truncate">
                      {(d.message_preview || '').slice(0, 80)}
                    </td>
                    <td style={{ fontSize: '0.78rem', color: '#888' }}>{formatTime(d.delivered_at || d.created_at)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Healing Stats Tab (deferred — only fetches when active)
// ---------------------------------------------------------------------------

const ASSESSMENT_COLOR_MAP: Record<string, string> = {
  good: '#2a9d8f', corrected: '#4361ee', filled: '#d4a019',
  flagged: '#e76f51', dropped: '#e63946',
}

function HealingStatsTab() {
  const healingStats = useHealingStats()
  const healingLog = useHealingLog(30)
  const hStats = healingStats.data

  if (healingStats.isLoading) return <p style={{ color: '#888', fontSize: '0.85rem' }}>Loading healing data...</p>

  if (!hStats) return <p style={{ color: '#888', fontSize: '0.85rem' }}>No healing data available</p>

  return (
    <div className="space-y-6">
      {hStats.latest_run && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <MetricCard label="Model" value={hStats.latest_run.model || '--'} />
          <MetricCard label="Tokens" value={
            hStats.latest_run.tokens_in != null
              ? `${hStats.latest_run.tokens_in} in / ${hStats.latest_run.tokens_out ?? 0} out`
              : '--'
          } />
          <MetricCard label="Latency" value={
            hStats.latest_run.latency_s != null
              ? `${hStats.latest_run.latency_s.toFixed(1)}s`
              : '--'
          } />
          <MetricCard label="Fallback Used" value={hStats.latest_run.fallback_used ? 'Yes' : 'No'} />
        </div>
      )}

      {hStats.assessment_distribution && (
        <div>
          <div className="section-header">Assessment Summary</div>
          <div className="flex flex-wrap gap-3">
            {Object.entries(hStats.assessment_distribution).map(([key, val]) => {
              const c = ASSESSMENT_COLOR_MAP[key] || '#888'
              return (
                <div key={key} style={{
                  background: `${c}15`, border: `1px solid ${c}40`,
                  padding: '8px 14px', borderRadius: '6px', textAlign: 'center',
                  minWidth: '90px',
                }}>
                  <div style={{ fontSize: '1.4rem', fontWeight: 700, color: c }}>{val.count}</div>
                  <div style={{
                    textTransform: 'uppercase', letterSpacing: '1px',
                    fontSize: '0.72rem', color: `${c}99`,
                  }}>{key}</div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      <div>
        <div className="section-header">Recent Healing Records</div>
        {(!healingLog.data || healingLog.data.length === 0) ? (
          <p style={{ color: '#888', fontSize: '0.85rem' }}>No healing records</p>
        ) : (
          <div className="space-y-2">
            {healingLog.data.slice(0, 15).map((h, i) => {
              const assessment = h.assessment || 'unknown'
              const color = ASSESSMENT_COLOR_MAP[assessment] || '#888'
              return (
                <div key={h.id ?? i} style={{
                  background: '#fff', border: '1px solid #e0dcd5', borderRadius: '8px',
                  padding: '10px 14px',
                }}>
                  <div className="flex items-center gap-2 flex-wrap">
                    <span style={{ fontWeight: 600, color: '#1a1a1a' }}>{h.station_id}</span>
                    <span style={{
                      background: `${color}22`, color, border: `1px solid ${color}44`,
                      padding: '1px 8px', borderRadius: '4px', fontSize: '0.72rem', fontWeight: 600,
                    }}>{assessment}</span>
                    {h.quality_score != null && (
                      <span style={{ fontSize: '0.78rem', color: '#888', marginLeft: 'auto' }}>
                        Quality: {(h.quality_score * 100).toFixed(0)}%
                      </span>
                    )}
                  </div>
                  {h.reasoning && (
                    <p style={{ fontSize: '0.82rem', color: '#555', lineHeight: 1.5, marginTop: '4px' }}>
                      {h.reasoning.slice(0, 200)}{h.reasoning.length > 200 ? '...' : ''}
                    </p>
                  )}
                  {h.tools_used && (
                    <div className="flex gap-1 flex-wrap mt-1">
                      {h.tools_used.split(',').map((tool: string, j: number) => (
                        <span key={j} style={{
                          background: '#f0ede8', border: '1px solid #d0ccc5',
                          borderRadius: '12px', padding: '2px 10px', fontSize: '0.72rem',
                        }}>{tool.trim()}</span>
                      ))}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function Pipeline() {
  const runs = usePipelineRuns(30)

  const [activeTab, setActiveTab] = useState(0)

  if (runs.isLoading) return <PageLoader label="Loading system data..." />

  const runList = runs.data ?? []
  const okRuns = runList.filter(r => r.status === 'ok' || r.status === 'success' || r.status === 'completed').length
  const failedRuns = runList.filter(r => r.status === 'failed' || r.status === 'error').length

  const TABS = [
    'Architecture', 'Scheduler', 'Pipeline Runs', 'Delivery Log',
    'Cost Estimate', 'Eval Metrics', 'Healing Stats', 'Agent Log', 'Delivery Funnel',
  ]

  return (
    <div className="space-y-6">
      <div>
        <h1 className="page-title">System Overview</h1>
        <p className="page-caption">
          Architecture, pipeline history, and infrastructure
        </p>
      </div>

      {/* Tabs */}
      <div className="tab-list">
        {TABS.map((tab, i) => (
          <button key={tab} className={`tab-item ${activeTab === i ? 'active' : ''}`} onClick={() => setActiveTab(i)}>
            {tab}
          </button>
        ))}
      </div>

      {/* Architecture */}
      {activeTab === 0 && <ArchitectureDiagram />}

      {/* Scheduler */}
      {activeTab === 1 && (
        <div className="space-y-6">
          <h2 className="text-lg font-semibold" style={{ color: '#1a1a1a' }}>
            Daily Pipeline Scheduler
          </h2>
          <p style={{ color: '#888', fontSize: '0.82rem' }}>
            Runs the full 6-step pipeline once per day at 6:00 AM IST (background thread)
          </p>

          {/* Toggle (display only in React — backend control) */}
          <label className="flex items-center gap-3 cursor-pointer">
            <div style={{
              width: '44px', height: '24px', borderRadius: '12px',
              background: '#e0dcd5', position: 'relative', transition: 'background 0.2s',
            }}>
              <div style={{
                width: '20px', height: '20px', borderRadius: '50%', background: '#fff',
                position: 'absolute', top: '2px', left: '2px',
                boxShadow: '0 1px 3px rgba(0,0,0,0.2)',
              }} />
            </div>
            <span style={{ fontSize: '0.85rem', color: '#555' }}>Enable daily pipeline run</span>
          </label>

          <p style={{ color: '#888', fontSize: '0.82rem', fontStyle: 'italic' }}>
            Scheduler is <strong>off</strong> — toggle on to start daily runs
          </p>

          {/* Schedule card */}
          <div style={{
            background: '#fff', border: '1px solid #e0dcd5', borderRadius: '8px', padding: '16px',
          }}>
            <div style={{ fontSize: '0.82rem', color: '#666' }}>Schedule</div>
            <div style={{ fontSize: '1.1rem', fontWeight: 600, color: '#1a1a1a' }}>
              Every day at 6:00 AM IST
            </div>
            <div style={{ fontSize: '0.78rem', color: '#888', marginTop: '6px' }}>
              APScheduler background thread (cron: 00:30 UTC)<br />
              State persists in <code>scheduler_state.json</code> — auto-resumes after restart
            </div>
          </div>

          {/* Recent runs */}
          {runList.length > 0 && (
            <div>
              <div className="section-header">Recent Runs</div>
              <div className="space-y-2">
                {runList.slice(0, 3).map((r, i) => {
                  const s = r.status || '?'
                  const color = STATUS_COLOR[s] || '#888'
                  const started = (r.started_at || '').slice(0, 16)
                  return (
                    <div key={r.id ?? i} className="flex items-center gap-3">
                      <span style={{
                        background: color, color: '#fff', padding: '2px 8px',
                        borderRadius: '3px', fontSize: '0.7rem', fontWeight: 600,
                      }}>{s}</span>
                      <span style={{ color: '#555', fontSize: '0.82rem' }}>{started}</span>
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* Manual controls */}
          <div>
            <div className="section-header">Manual Controls</div>
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
              {['Run Full Pipeline', 'Ingest + Heal', 'Forecast \u2192 Deliver', 'Retrain MOS Model'].map(label => (
                <button
                  key={label}
                  className="btn-secondary w-full"
                  style={{ fontSize: '0.78rem' }}
                  onClick={() => alert(`${label}: would trigger via API (not yet wired)`)}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Pipeline Runs */}
      {activeTab === 2 && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
            <MetricCard label="Total Runs" value={runList.length} />
            <MetricCard label="Successful" value={okRuns} />
            <MetricCard label="Partial / Failed" value={failedRuns + runList.filter(r => r.status === 'partial').length} />
          </div>

          {runList.length === 0 ? (
            <div className="card card-body text-center py-8">
              <p style={{ color: '#888', fontSize: '0.85rem' }}>No pipeline runs recorded</p>
            </div>
          ) : (
            <div className="table-container">
              <table>
                <thead>
                  <tr>
                    <th>Status</th>
                    <th>Run ID</th>
                    <th>Started</th>
                    <th>Duration</th>
                    <th>Stations</th>
                    <th>Records</th>
                    <th>Summary</th>
                  </tr>
                </thead>
                <tbody>
                  {runList.map((r, i) => {
                    const s = r.status || '?'
                    const color = STATUS_COLOR[s] || '#888'
                    return (
                      <tr key={r.id ?? i}>
                        <td>
                          <span style={{
                            background: color, color: '#fff', padding: '2px 10px',
                            borderRadius: '5px', fontSize: '0.68rem', fontWeight: 700,
                            display: 'inline-block', minWidth: '50px', textAlign: 'center',
                          }}>{s}</span>
                        </td>
                        <td style={{ fontFamily: 'monospace', fontSize: '0.75rem', color: '#aaa' }}>
                          {(r.run_id || r.id?.toString() || '').slice(0, 8)}
                        </td>
                        <td style={{ fontSize: '0.82rem' }}>{formatTime(r.started_at)}</td>
                        <td>
                          {r.duration_seconds != null ? `${r.duration_seconds.toFixed(1)}s` : '--'}
                        </td>
                        <td>{r.stations_processed ?? '--'}</td>
                        <td>{r.records_ingested ?? '--'}</td>
                        <td style={{ fontSize: '0.82rem', color: '#555', maxWidth: '200px' }} className="truncate">
                          {(r.error_detail || '').slice(0, 80) || '--'}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Delivery Log */}
      {activeTab === 3 && <SystemDeliveryLogTab />}

      {/* Cost Estimate */}
      {activeTab === 4 && (
        <div className="space-y-6">
          <div className="section-header">API Cost Estimate (per pipeline run)</div>
          <div className="table-container">
            <table>
              <thead>
                <tr><th>Component</th><th>Unit Cost</th><th>Est. per Run</th><th>Notes</th></tr>
              </thead>
              <tbody>
                <tr><td style={{ fontWeight: 500 }}>Claude Healing (Sonnet)</td><td>~$3/M tokens</td><td>~$0.15</td><td>20 stations, ~500 tokens each</td></tr>
                <tr><td style={{ fontWeight: 500 }}>Claude Advisory (Sonnet)</td><td>~$3/M tokens</td><td>~$0.08</td><td>20 advisories, RAG context</td></tr>
                <tr><td style={{ fontWeight: 500 }}>Claude Translation</td><td>~$3/M tokens</td><td>~$0.04</td><td>20 translations (Tamil/Malayalam)</td></tr>
                <tr><td style={{ fontWeight: 500 }}>Tomorrow.io</td><td>Free tier</td><td>$0.00</td><td>500 calls/day free</td></tr>
                <tr><td style={{ fontWeight: 500 }}>Open-Meteo</td><td>Free</td><td>$0.00</td><td>No API key needed</td></tr>
                <tr><td style={{ fontWeight: 500 }}>NASA POWER</td><td>Free</td><td>$0.00</td><td>Public API</td></tr>
                <tr><td style={{ fontWeight: 500 }}>NeuralGCM (GPU)</td><td>~$0.80/hr (L4)</td><td>~$0.02</td><td>~90s inference on L4</td></tr>
              </tbody>
            </table>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div style={{
              background: '#fff', border: '1px solid #e0dcd5', borderRadius: '8px', padding: '16px',
            }}>
              <div className="section-header">Per-Run Total</div>
              <div style={{ fontSize: '2rem', fontWeight: 700, color: '#d4a019' }}>~$0.29</div>
              <div style={{ color: '#666', fontSize: '0.82rem' }}>
                Claude: ~$0.27 + GPU: ~$0.02
              </div>
              <div style={{ color: '#2a9d8f', fontSize: '0.82rem', marginTop: '4px' }}>
                Fallback (no Claude): ~$0.02/run
              </div>
            </div>
            <div style={{
              background: '#fff', border: '1px solid #e0dcd5', borderRadius: '8px', padding: '16px',
            }}>
              <div className="section-header">Monthly Estimate (1x/day)</div>
              <div style={{ fontSize: '2rem', fontWeight: 700, color: '#d4a019' }}>~$9/mo</div>
              <div style={{ color: '#666', fontSize: '0.82rem' }}>
                30 runs/month at ~$0.29 each
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Eval Metrics */}
      {activeTab === 5 && <EvalMetricsTab />}

      {/* Healing Stats */}
      {activeTab === 6 && <HealingStatsTab />}

      {/* Agent Log */}
      {activeTab === 7 && <AgentLogTab />}

      {/* Delivery Funnel */}
      {activeTab === 8 && <DeliveryFunnelTab />}
    </div>
  )
}
