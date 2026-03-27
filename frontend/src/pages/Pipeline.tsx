import { useState } from 'react'
import {
  usePipelineRuns, useHealingStats, useHealingLog, usePipelineStats,
  useDeliveryLog, useEvals, useConversationLog, useDeliveryMetricsAgg,
} from '../api/hooks'
import { MetricCard } from '../components/MetricCard'
import { TableSkeleton } from '../components/LoadingSpinner'
import { PageContext } from '../components/PageContext'

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
  { emoji: '\uD83D\uDD27', name: 'IMD / imdlib', desc: 'Station observations', color: '#2E7D32' },
  { emoji: '\uD83C\uDF10', name: 'Tomorrow.io', desc: 'Cross-validation ref', color: '#1565C0' },
  { emoji: '\uD83D\uDCE1', name: 'NeuralGCM / Open-Meteo', desc: 'NWP forecasts', color: '#7B1FA2' },
  { emoji: '\uD83D\uDEF0\uFE0F', name: 'NASA POWER', desc: 'Spatial grid (0.5\u00B0)', color: '#E65100' },
  { emoji: '\uD83E\uDD16', name: 'Claude API', desc: 'Advisory + Translation', color: '#C62828' },
]

const PIPELINE_STEPS = [
  { num: 1, name: 'Ingest', table: 'raw_telemetry', desc: 'IMD station data', color: '#2E7D32' },
  { num: 2, name: 'Heal', table: 'clean_telemetry', desc: 'Anomaly detection + imputation', color: '#1565C0' },
  { num: 3, name: 'Forecast', table: 'forecasts', desc: 'MOS: NWP + XGBoost residual', color: '#7B1FA2' },
  { num: 4, name: 'Downscale', table: 'forecasts', desc: 'IDW + lapse-rate to farmer GPS', color: '#E65100' },
  { num: 5, name: 'Translate', table: 'agricultural_alerts', desc: 'RAG + Claude advisory', color: '#C62828' },
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

const DB_TABLES = [
  'raw_telemetry', 'clean_telemetry', 'forecasts', 'agricultural_alerts', 'delivery_log',
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
            </div>
          ))}
        </div>
      </div>

      {/* Vertical flow indicator */}
      <div style={{ textAlign: 'center', color: '#d4a019', fontSize: '1.5rem', lineHeight: 1 }}>
        \u25BC \u25BC \u25BC
      </div>

      {/* Pipeline Steps — vertical flow */}
      <div>
        <div style={{
          fontSize: '0.72rem', fontWeight: 600, textTransform: 'uppercase' as const,
          letterSpacing: '1.5px', color: '#888', marginBottom: '10px',
        }}>
          Pipeline (6 steps, linear)
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0', paddingLeft: '20px' }}>
          {PIPELINE_STEPS.map((s, i) => (
            <div key={s.num}>
              <div style={{ display: 'flex', alignItems: 'flex-start', gap: '14px' }}>
                {/* Step number circle */}
                <div style={{
                  width: '36px', height: '36px', borderRadius: '50%', background: s.color,
                  color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontWeight: 700, fontSize: '0.85rem', flexShrink: 0,
                }}>
                  {s.num}
                </div>
                {/* Card */}
                <div style={{
                  flex: 1, background: '#fff', border: '1px solid #e0dcd5', borderRadius: '8px',
                  padding: '12px 16px',
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
                    <span style={{ fontWeight: 700, fontSize: '0.9rem', color: s.color }}>{s.name}</span>
                    <code style={{
                      background: '#f0ede8', padding: '2px 8px', borderRadius: '4px',
                      fontSize: '0.72rem', color: '#555',
                    }}>{s.table}</code>
                  </div>
                  <div style={{ fontSize: '0.8rem', color: '#666', marginTop: '4px' }}>{s.desc}</div>
                </div>
              </div>
              {/* Connector line */}
              {i < PIPELINE_STEPS.length - 1 && (
                <div style={{
                  width: '2px', height: '16px', background: '#d4a019', marginLeft: '17px',
                }} />
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
              <span style={{ color: '#d4a019', fontSize: '0.9rem' }}>{'\u2192'}</span>
              <span style={{ fontSize: '0.78rem', color: '#2a9d8f', fontWeight: 500 }}>
                {d.fallback}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Database Tables */}
      <div>
        <div style={{
          fontSize: '0.72rem', fontWeight: 600, textTransform: 'uppercase' as const,
          letterSpacing: '1.5px', color: '#888', marginBottom: '10px',
        }}>
          Database (core tables)
        </div>
        <div style={{
          display: 'flex', alignItems: 'center', gap: '0', flexWrap: 'wrap',
          background: '#fff', border: '1px solid #e0dcd5', borderRadius: '8px',
          padding: '12px 16px',
        }}>
          {DB_TABLES.map((t, i) => (
            <div key={t} style={{ display: 'flex', alignItems: 'center' }}>
              <code style={{
                background: '#f0ede8', padding: '4px 10px', borderRadius: '4px',
                fontSize: '0.76rem', fontWeight: 500, color: '#1a1a1a',
              }}>{t}</code>
              {i < DB_TABLES.length - 1 && (
                <span style={{ color: '#d4a019', margin: '0 8px', fontSize: '0.85rem' }}>{'\u2192'}</span>
              )}
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

const EVAL_SCRIPTS = [
  { cmd: 'python tests/eval_healing.py', label: 'Self-Healing Detection', desc: 'Tests anomaly detection precision/recall and imputation accuracy' },
  { cmd: 'python tests/eval_forecast.py', label: 'Forecast Accuracy', desc: 'Evaluates MAE/RMSE of MOS-corrected forecasts vs observations' },
  { cmd: 'python tests/eval_rag.py', label: 'RAG Retrieval', desc: 'Measures precision@5 and recall of hybrid FAISS+BM25 retrieval' },
  { cmd: 'python tests/eval_advisory.py', label: 'Advisory Quality', desc: 'Scores advisory accuracy, actionability, safety, and cultural fit' },
  { cmd: 'python tests/eval_translation.py', label: 'Translation Quality', desc: 'Evaluates semantic similarity and agricultural term preservation' },
  { cmd: 'python tests/eval_dpi.py', label: 'DPI Coverage', desc: 'Checks DPI profile completeness, station coverage, and consistency' },
  { cmd: 'python tests/eval_conversation.py', label: 'Conversation Engine', desc: 'Tests state machine, language detection, and escalation accuracy' },
]

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
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3" style={{ textAlign: 'left' }}>
            {EVAL_SCRIPTS.map(e => (
              <button
                key={e.cmd}
                className="btn-secondary"
                title={e.desc}
                style={{ fontSize: '0.78rem', textAlign: 'left', padding: '10px 14px' }}
                onClick={() => alert(`Run this from your terminal:\n${e.cmd}`)}
              >
                <div style={{ fontWeight: 600, marginBottom: '2px' }}>{e.label}</div>
                <code style={{ fontSize: '0.72rem', color: '#888' }}>{e.cmd}</code>
              </button>
            ))}
          </div>
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

  // Cost calculator state
  const [stationCount, setStationCount] = useState(20)
  const [runsPerWeek, setRunsPerWeek] = useState(1)
  const [claudeModel, setClaudeModel] = useState<'sonnet' | 'haiku'>('sonnet')

  if (runs.isLoading) return <TableSkeleton />

  const runList = runs.data ?? []
  const okRuns = runList.filter(r => r.status === 'ok' || r.status === 'success' || r.status === 'completed').length
  const failedRuns = runList.filter(r => r.status === 'failed' || r.status === 'error').length

  const TABS = ['Pipeline Runs', 'Pipeline Stats', 'Build Your Own']

  // Cost calculator derived values
  const perRunCost = (stationCount / 20) * (claudeModel === 'sonnet' ? 0.27 : 0.03) + 0.02
  const monthlyCost = perRunCost * runsPerWeek * 4.33

  return (
    <div className="space-y-6">
      <div>
        <h1 className="page-title">System</h1>
        <p className="page-caption">
          Pipeline operations, quality metrics, and deployment
        </p>
      </div>

      <PageContext id="pipeline">
        The pipeline runs 6 steps weekly via GitHub Actions, with independent degradation chains ensuring no single API failure cascades.
      </PageContext>

      {/* Tabs */}
      <div className="tab-list">
        {TABS.map((tab, i) => (
          <button key={tab} className={`tab-item ${activeTab === i ? 'active' : ''}`} onClick={() => setActiveTab(i)}>
            {tab}
          </button>
        ))}
      </div>

      {/* Tab 0: Pipeline Runs (with Scheduler compact card at top) */}
      {activeTab === 0 && (
        <div className="space-y-6">
          {/* Scheduler compact card */}
          <div style={{
            background: '#fff', border: '1px solid #e0dcd5', borderRadius: '8px',
            padding: '16px', display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '16px',
          }}>
            <div style={{ flex: '1 1 auto', minWidth: '200px' }}>
              <div style={{ fontWeight: 600, fontSize: '0.88rem', color: '#1a1a1a', marginBottom: '4px' }}>
                Weekly Pipeline Schedule
              </div>
              <div style={{ fontSize: '0.78rem', color: '#888' }}>
                Runs every Monday at 06:00 IST via GitHub Actions. The pipeline processes all stations in ~6 minutes.
              </div>
            </div>

            {/* Manual controls */}
            <div style={{ flexBasis: '100%' }}>
              <div className="grid grid-cols-2 gap-3" style={{ maxWidth: '400px' }}>
                <button
                  className="btn-secondary w-full"
                  style={{ fontSize: '0.78rem' }}
                  title="Triggers all 6 pipeline steps: ingest weather data, heal anomalies, generate forecasts, downscale to farmer GPS, create advisories, and deliver via SMS"
                  onClick={() => alert('Run Full Pipeline: would trigger via API (not yet wired)')}
                >
                  Run Full Pipeline
                </button>
                <button
                  className="btn-secondary w-full"
                  style={{ fontSize: '0.78rem' }}
                  title="Re-trains the XGBoost Model Output Statistics correction model on the latest observation-forecast pairs. Improves forecast accuracy over time."
                  onClick={() => alert('Retrain MOS Model: would trigger via API (not yet wired)')}
                >
                  Retrain MOS Model
                </button>
              </div>
            </div>

            {/* Recent runs (compact) */}
            {runList.length > 0 && (
              <div style={{ flexBasis: '100%' }}>
                <div style={{ fontSize: '0.72rem', fontWeight: 600, textTransform: 'uppercase' as const, letterSpacing: '1px', color: '#888', marginBottom: '6px' }}>
                  Recent Runs
                </div>
                <div className="flex gap-3 flex-wrap">
                  {runList.slice(0, 3).map((r, i) => {
                    const s = r.status || '?'
                    const color = STATUS_COLOR[s] || '#888'
                    const started = (r.started_at || '').slice(0, 16)
                    return (
                      <div key={r.id ?? i} className="flex items-center gap-2">
                        <span style={{
                          background: color, color: '#fff', padding: '2px 8px',
                          borderRadius: '3px', fontSize: '0.7rem', fontWeight: 600,
                        }}>{s}</span>
                        <span style={{ color: '#555', fontSize: '0.78rem' }}>{started}</span>
                      </div>
                    )
                  })}
                </div>
              </div>
            )}
          </div>

          {/* Run history table */}
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
        </div>
      )}

      {/* Tab 1: Pipeline Stats (Quality + Delivery + Agent Log) */}
      {activeTab === 1 && (
        <div className="space-y-8">
          {/* Healing Stats */}
          <div>
            <div className="section-header" style={{ fontSize: '0.88rem', marginBottom: '12px' }}>Healing Stats</div>
            <HealingStatsTab />
          </div>
          <hr style={{ border: 'none', borderTop: '1px solid #e0dcd5' }} />

          {/* Eval Metrics */}
          <div>
            <div className="section-header" style={{ fontSize: '0.88rem', marginBottom: '12px' }}>Eval Metrics</div>
            <EvalMetricsTab />
          </div>
          <hr style={{ border: 'none', borderTop: '1px solid #e0dcd5' }} />

          {/* Delivery Funnel + Log */}
          <DeliveryFunnelTab />
          <hr style={{ border: 'none', borderTop: '1px solid #e0dcd5' }} />
          <div>
            <div className="section-header" style={{ fontSize: '0.88rem', marginBottom: '12px' }}>Delivery Log</div>
            <SystemDeliveryLogTab />
          </div>
          <hr style={{ border: 'none', borderTop: '1px solid #e0dcd5' }} />

          {/* Agent Log */}
          <div>
            <div className="section-header" style={{ fontSize: '0.88rem', marginBottom: '12px' }}>Agent Log</div>
            <AgentLogTab />
          </div>
        </div>
      )}

      {/* Tab 2: Build Your Own */}
      {activeTab === 2 && (
        <div className="space-y-6">
          <div className="section-header">Fork This Pipeline for Your Location</div>

          <div className="card card-body">
            <p style={{ fontSize: '0.85rem', color: '#555', lineHeight: 1.7 }}>
              This entire pipeline can be adapted for any region in the world.
              Copy the prompt below, open <a href="https://claude.ai/code" target="_blank" rel="noopener" style={{ color: '#d4a019', fontWeight: 600 }}>Claude Code</a> in a fork of this repo, and paste it.
            </p>
          </div>

          {/* The one-shot prompt in a styled code block */}
          <div>
            <div className="section-header">One-Shot Prompt</div>
            <pre style={{
              background: '#1a1a1a', color: '#e0dcd5', borderRadius: '8px',
              padding: '20px', fontSize: '0.82rem', lineHeight: 1.7,
              overflow: 'auto', whiteSpace: 'pre-wrap',
            }}>
{`I want to adapt this weather pipeline for [YOUR REGION]. Here are my stations:

1. [City Name], lat: [XX.XX], lon: [XX.XX], altitude: [XXm], crops: [crop1, crop2]
2. [City Name], lat: [XX.XX], lon: [XX.XX], altitude: [XXm], crops: [crop1, crop2]
... (5-10 stations)

Language for advisories: [language code, e.g. "es" for Spanish, "fr" for French]
Region name: [e.g. "Central Mexico", "Northern France"]

Please:
1. Generate a new stations.json with my stations
2. Set ingestion_source to "open_meteo" in config (since I don't have IMD)
3. Update the dashboard title and subtitle for my region
4. Update CLAUDE.md with the new station list
5. Skip the DPI/farmer services (India-specific)
6. Test that the pipeline runs with python run_pipeline.py`}
            </pre>
          </div>

          {/* What works globally */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="card card-body">
              <div style={{ fontWeight: 600, color: '#2a9d8f', marginBottom: '8px', fontSize: '0.85rem' }}>
                Works Globally (no changes needed)
              </div>
              <ul style={{ fontSize: '0.82rem', color: '#555', lineHeight: 1.8, paddingLeft: '16px', margin: 0 }}>
                <li>Open-Meteo weather data (global, free)</li>
                <li>NASA POWER satellite data (global)</li>
                <li>NeuralGCM forecasting (global neural weather model)</li>
                <li>Claude advisory generation (any language)</li>
                <li>XGBoost MOS correction (trains on local data)</li>
                <li>PostgreSQL, FAISS RAG, pipeline orchestration</li>
              </ul>
            </div>
            <div className="card card-body">
              <div style={{ fontWeight: 600, color: '#e65100', marginBottom: '8px', fontSize: '0.85rem' }}>
                India-Specific (the prompt handles this)
              </div>
              <ul style={{ fontSize: '0.82rem', color: '#555', lineHeight: 1.8, paddingLeft: '16px', margin: 0 }}>
                <li>IMD/imdlib ingestion {'\u2192'} replaced by Open-Meteo</li>
                <li>Tamil/Malayalam {'\u2192'} replaced by your language</li>
                <li>Kerala/TN crop context {'\u2192'} replaced by your crops</li>
                <li>DPI services (Aadhaar, PM-KISAN) {'\u2192'} skipped</li>
              </ul>
            </div>
          </div>

          {/* Cost Calculator */}
          <div>
            <div className="section-header">Cost Calculator</div>
            <div style={{
              background: '#fff', border: '1px solid #e0dcd5', borderRadius: '8px',
              padding: '20px',
            }}>
              <p style={{ fontSize: '0.82rem', color: '#666', marginBottom: '16px' }}>
                Estimate the running cost for your deployment based on station count, run frequency, and Claude model choice.
              </p>
              <div style={{ display: 'flex', gap: '20px', flexWrap: 'wrap', marginBottom: '20px' }}>
                <label style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  <span style={{ fontSize: '0.75rem', fontWeight: 600, color: '#888', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Stations</span>
                  <input type="number" min={1} max={200} step={5} value={stationCount}
                    onChange={e => setStationCount(Math.max(1, Math.min(200, Number(e.target.value))))}
                    className="input" style={{ width: '90px' }} />
                </label>
                <label style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  <span style={{ fontSize: '0.75rem', fontWeight: 600, color: '#888', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Runs/week</span>
                  <input type="number" min={1} max={28} step={1} value={runsPerWeek}
                    onChange={e => setRunsPerWeek(Math.max(1, Math.min(28, Number(e.target.value))))}
                    className="input" style={{ width: '90px' }} />
                </label>
                <label style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  <span style={{ fontSize: '0.75rem', fontWeight: 600, color: '#888', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Claude model</span>
                  <select value={claudeModel} onChange={e => setClaudeModel(e.target.value as 'sonnet' | 'haiku')}
                    className="input">
                    <option value="sonnet">Sonnet (~$3/M tokens)</option>
                    <option value="haiku">Haiku (~$0.25/M tokens)</option>
                  </select>
                </label>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div style={{ background: '#faf8f5', border: '1px solid #e0dcd5', borderRadius: '8px', padding: '16px' }}>
                  <div style={{ fontSize: '0.72rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '1px', color: '#888', marginBottom: '6px' }}>Per-Run Cost</div>
                  <div style={{ fontSize: '2rem', fontWeight: 700, color: '#d4a019' }}>~${perRunCost.toFixed(2)}</div>
                  <div style={{ color: '#666', fontSize: '0.82rem', marginTop: '4px' }}>
                    Claude: ~${(perRunCost - 0.02).toFixed(2)} + GPU: ~$0.02
                  </div>
                </div>
                <div style={{ background: '#faf8f5', border: '1px solid #e0dcd5', borderRadius: '8px', padding: '16px' }}>
                  <div style={{ fontSize: '0.72rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '1px', color: '#888', marginBottom: '6px' }}>Monthly Estimate</div>
                  <div style={{ fontSize: '2rem', fontWeight: 700, color: '#d4a019' }}>~${monthlyCost.toFixed(2)}/mo</div>
                  <div style={{ color: '#666', fontSize: '0.82rem', marginTop: '4px' }}>
                    {runsPerWeek}x/week {'\u00D7'} 4.33 weeks {'\u00D7'} ${perRunCost.toFixed(2)}/run
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
