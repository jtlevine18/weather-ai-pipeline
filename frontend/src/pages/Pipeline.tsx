import { useState } from 'react'
import {
  usePipelineRuns, useHealingStats, useHealingLog, usePipelineStats,
  useDeliveryLog, useEvals, useConversationLog, useDeliveryMetricsAgg,
} from '../api/hooks'
import { MetricCard } from '../components/MetricCard'
import { TableSkeleton } from '../components/LoadingSpinner'
import { TabPanel } from '../components/TabPanel'
import { REGION, languageName } from '../regionConfig'
import { formatTimeShort as formatTime } from '../lib/format'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const STACK = [
  {
    label: 'Data',
    items: ['IMD station API (data.gov.in)', '20 ground stations', 'Kerala + Tamil Nadu'],
  },
  {
    label: 'Models',
    items: ['NeuralGCM (Google DeepMind)', 'Claude Sonnet for advisories', 'Claude Haiku for Tamil / Malayalam'],
  },
  {
    label: 'Delivery',
    items: ['Twilio SMS', 'Weekly broadcast', 'Bilingual per farmer'],
  },
  {
    label: 'Infrastructure',
    items: ['Postgres on Neon', 'Hugging Face Spaces', 'GitHub Actions cron', 'Vercel frontend'],
  },
]

function HowItWorksSection() {
  return (
    <div>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(4, minmax(0, 1fr))',
          gap: '28px',
          borderTop: '1px solid #e8e5e1',
          paddingTop: '18px',
        }}
      >
        {STACK.map((cat) => (
          <div key={cat.label}>
            <div className="eyebrow">{cat.label}</div>
            <ul
              style={{
                listStyle: 'none',
                padding: 0,
                margin: '12px 0 0 0',
                fontFamily: '"Space Grotesk", system-ui, sans-serif',
                fontSize: '13px',
                lineHeight: 1.7,
                color: '#606373',
              }}
            >
              {cat.items.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </div>
  )
}

const STATUS_COLOR: Record<string, string> = {
  ok: '#606373', success: '#606373', completed: '#606373',
  partial: '#2d5b7d', running: '#606373',
  failed: '#c71f48', error: '#c71f48',
}

const DELIVERY_STATUS_COLOR: Record<string, string> = {
  sent: '#606373', dry_run: '#606373', failed: '#c71f48',
}

// ---------------------------------------------------------------------------
// Eval Metrics Tab
// ---------------------------------------------------------------------------

const EVAL_SCRIPTS = [
  { cmd: 'python tests/eval_healing.py', label: 'Cleaning detection', desc: 'Tests anomaly detection precision and recall and filled-reading accuracy' },
  { cmd: 'python tests/eval_forecast.py', label: 'Forecast Accuracy', desc: 'Evaluates forecast accuracy against observations' },
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
          <p style={{ color: '#888', fontSize: '0.9rem' }}>No eval results available yet.</p>
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
            <div className="section-header">Cleaning detection</div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
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
            <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
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
                                <td style={{ fontWeight: 500 }}>{languageName(lang)}</td>
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
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
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
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
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
          No conversation logs yet. Open the chat widget in the bottom-right to start a conversation.
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
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
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
          No delivery metrics yet.
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
    { label: 'Advisories', value: totalAdvisories, color: '#2d5b7d' },
    { label: 'Attempted', value: totalAttempted, color: '#E65100' },
    { label: 'Succeeded', value: totalSucceeded, color: '#606373' },
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
        background: '#fff', border: '1px solid #e8e5e1', borderRadius: '8px', padding: '16px',
      }}>
        {funnel.map(f => (
          <div key={f.label} style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '8px' }}>
            <div style={{ width: '90px', fontSize: '0.78rem', fontWeight: 500, color: '#555', textAlign: 'right' }}>
              {f.label}
            </div>
            <div style={{ flex: 1, background: '#f0ece6', borderRadius: '4px', height: '24px', overflow: 'hidden' }}>
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
                  <td style={{ color: rate !== '--' && parseFloat(rate) >= 90 ? '#606373' : '#c71f48' }}>
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
      <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
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
                      {(d.message || '').slice(0, 80)}
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
  good: '#606373', corrected: '#606373', filled: '#2d5b7d',
  flagged: '#e76f51', dropped: '#c71f48',
}

function HealingStatsTab() {
  const healingStats = useHealingStats()
  const healingLog = useHealingLog(30)
  const hStats = healingStats.data

  if (healingStats.isLoading) return <p style={{ color: '#888', fontSize: '0.85rem' }}>Loading cleaning data...</p>

  if (!hStats) return <p style={{ color: '#888', fontSize: '0.85rem' }}>No cleaning data available</p>

  return (
    <div className="space-y-6">
      {hStats.latest_run && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
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
        <div className="section-header">Recent cleaning records</div>
        {(!healingLog.data || healingLog.data.length === 0) ? (
          <p style={{ color: '#888', fontSize: '0.85rem' }}>No cleaning records</p>
        ) : (
          <div className="space-y-2">
            {healingLog.data.slice(0, 15).map((h, i) => {
              const assessment = h.assessment || 'unknown'
              const color = ASSESSMENT_COLOR_MAP[assessment] || '#888'
              return (
                <div key={h.id ?? i} style={{
                  background: '#fff', border: '1px solid #e8e5e1', borderRadius: '8px',
                  padding: '10px 14px',
                }}>
                  <div className="flex items-center gap-2 flex-wrap">
                    <span style={{ fontWeight: 600, color: '#1b1e2d' }}>{h.station_id}</span>
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
                          background: '#f0ece6', border: '1px solid #d0ccc5',
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

// ---------------------------------------------------------------------------
// Scaling cost panel — shows what the pipeline costs at three tiers of
// personalization, making the "per-user cost is decoupled from LLM cost"
// design point concrete. Plain cards, no animations.
// ---------------------------------------------------------------------------

function ScalingCostPanel() {
  const TIERS = [
    {
      label: 'Current (live)',
      scale: '2,000 farmers · broadcast advisory',
      cost: '~$0.30 / week',
      note: 'One advisory per station, delivered to every farmer in that station\u2019s radius. 10 featured farmers also get a personalized version.',
      color: '#606373',
    },
    {
      label: 'Full personalization',
      scale: '2,000 farmers · advisory per farmer',
      cost: '~$6 / week',
      note: 'Every farmer gets an advisory tailored to their crops, soil, irrigation, and land size. Weekly run.',
      color: '#1565C0',
    },
    {
      label: 'State-wide',
      scale: '10,000 farmers · advisory per farmer',
      cost: '~$30 / week',
      note: 'Full state extension network. The model cost still scales linearly — the pipeline, not the bill, is what has to keep up.',
      color: '#2d5b7d',
    },
  ]

  return (
    <div style={{ marginTop: '32px' }}>
      <div className="section-header">What it costs to run at pilot scale</div>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(3, 1fr)',
          gap: '32px',
        }}
      >
        {TIERS.map(tier => (
          <div
            key={tier.label}
            style={{
              borderTop: '1px solid #e8e5e1',
              paddingTop: '16px',
            }}
          >
            <div className="eyebrow">{tier.label}</div>
            <div
              style={{
                fontFamily: '"Source Serif 4", Georgia, serif',
                fontSize: '28px',
                lineHeight: '34px',
                color: '#1b1e2d',
                marginTop: '12px',
                fontVariantNumeric: 'tabular-nums',
              }}
            >
              {tier.cost}
            </div>
            <div style={{ fontSize: '13px', color: '#606373', marginTop: '6px' }}>
              {tier.scale}
            </div>
            <p style={{ fontSize: '13px', color: '#8d909e', marginTop: '10px', lineHeight: 1.6 }}>
              {tier.note}
            </p>
          </div>
        ))}
      </div>
      <p
        style={{
          fontSize: '12px',
          color: '#8d909e',
          marginTop: '20px',
          fontStyle: 'italic',
          maxWidth: '780px',
          lineHeight: 1.6,
        }}
      >
        2,000 farmers live in the registry right now, distributed 100 per
        station across Kerala and Tamil Nadu. Broadcast delivery goes to all
        of them every run; per-farmer personalization runs for 10 featured
        farmers so the capability is visible without the bill scaling.
      </p>
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

  const TABS = ['Run History', 'Cost & scale', 'Build Your Own']

  // Cost calculator derived values
  const perRunCost = (stationCount / 20) * (claudeModel === 'sonnet' ? 0.27 : 0.03) + 0.02
  const monthlyCost = perRunCost * runsPerWeek * 4.33

  return (
    <div className="space-y-5">
      <div>
        <h1 className="page-title" data-tour="pipeline-title">
          How it works
        </h1>
        <button
          type="button"
          onClick={() => window.dispatchEvent(new Event('relaunch-tour'))}
          className="text-link"
          style={{ marginTop: '12px' }}
        >
          Take the guided tour →
        </button>
      </div>

      {/* Stack */}
      <HowItWorksSection />

      {/* Tabs */}
      <div className="tab-list">
        {TABS.map((tab, i) => (
          <button key={tab} className={`tab-item ${activeTab === i ? 'active' : ''}`} onClick={() => setActiveTab(i)}>
            {tab}
          </button>
        ))}
      </div>

      {/* Tab 0: Run History */}
      <TabPanel active={activeTab === 0}>
        <div className="space-y-6">
          {/* Scheduler caption */}
          <div
            style={{
              borderTop: '1px solid #e8e5e1',
              paddingTop: '16px',
              display: 'flex',
              flexWrap: 'wrap',
              alignItems: 'baseline',
              gap: '16px',
            }}
          >
            <div style={{ flex: '1 1 auto', minWidth: '200px' }}>
              <div className="eyebrow">Schedule</div>
              <div
                style={{
                  fontSize: '14px',
                  color: '#606373',
                  lineHeight: 1.6,
                  marginTop: '8px',
                  maxWidth: '620px',
                }}
              >
                Runs every Monday at 06:00 {REGION.timezoneLabel}. The
                pipeline processes all stations in about six minutes.
              </div>
            </div>

            {/* Recent runs (compact) */}
            {runList.length > 0 && (
              <div style={{ flexBasis: '100%', marginTop: '8px' }}>
                <div className="eyebrow" style={{ marginBottom: '8px' }}>Recent runs</div>
                <div className="flex gap-6 flex-wrap">
                  {runList.slice(0, 3).map((r, i) => {
                    const s = r.status || '?'
                    const color = STATUS_COLOR[s] || '#606373'
                    const started = (r.started_at || '').slice(0, 16)
                    return (
                      <div key={r.id ?? i} style={{ display: 'flex', alignItems: 'baseline', gap: '10px', fontSize: '13px' }}>
                        <span style={{ color, fontWeight: 500 }}>{s}</span>
                        <span style={{ color: '#606373' }}>{started}</span>
                      </div>
                    )
                  })}
                </div>
              </div>
            )}
          </div>

          {/* Run history table */}
          <div className="space-y-4">
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(3, 1fr)',
                gap: '32px',
                borderTop: '1px solid #e8e5e1',
                paddingTop: '20px',
                marginTop: '16px',
              }}
            >
              <MetricCard label="Total runs" value={runList.length} />
              <MetricCard label="Successful" value={okRuns} />
              <MetricCard label="Partial / failed" value={failedRuns + runList.filter(r => r.status === 'partial').length} />
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
                            <span style={{ color, fontSize: '13px', fontWeight: 500 }}>
                              {s}
                            </span>
                          </td>
                          <td style={{ fontVariantNumeric: 'tabular-nums', color: '#8d909e' }}>
                            {(r.run_id || r.id?.toString() || '').slice(0, 8)}
                          </td>
                          <td>{formatTime(r.started_at)}</td>
                          <td className="num">
                            {r.duration_seconds != null ? `${r.duration_seconds.toFixed(1)}s` : '—'}
                          </td>
                          <td className="num">{r.stations_processed ?? '—'}</td>
                          <td className="num">{r.records_ingested ?? '—'}</td>
                          <td style={{ color: '#606373', maxWidth: '200px' }} className="truncate">
                            {(r.error_detail || '').slice(0, 80) || '—'}
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
      </TabPanel>

      {/* Tab 1: Cost & scale */}
      <TabPanel active={activeTab === 1}>
        <div className="space-y-8">
          <ScalingCostPanel />

          {/* Cost Calculator */}
          <div>
            <div className="section-header">Customize for your region</div>
            <div style={{
              background: '#ffffff', border: '1px solid #e8e5e1', borderRadius: '4px',
              padding: '20px',
            }}>
              <p style={{ fontSize: '13px', color: '#606373', marginBottom: '16px', lineHeight: 1.6 }}>
                Estimate the running cost for your deployment based on station count, run frequency, and Claude model choice.
              </p>
              <div style={{ display: 'flex', gap: '20px', flexWrap: 'wrap', marginBottom: '20px' }}>
                <label style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  <span className="eyebrow">Stations</span>
                  <input type="number" min={1} max={200} step={5} value={stationCount}
                    onChange={e => setStationCount(Math.max(1, Math.min(200, Number(e.target.value))))}
                    className="input" style={{ width: '90px' }} />
                </label>
                <label style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  <span className="eyebrow">Runs / week</span>
                  <input type="number" min={1} max={28} step={1} value={runsPerWeek}
                    onChange={e => setRunsPerWeek(Math.max(1, Math.min(28, Number(e.target.value))))}
                    className="input" style={{ width: '90px' }} />
                </label>
                <label style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  <span className="eyebrow">model choice</span>
                  <select value={claudeModel} onChange={e => setClaudeModel(e.target.value as 'sonnet' | 'haiku')}
                    className="input">
                    <option value="sonnet">Sonnet (~$3/M tokens)</option>
                    <option value="haiku">Haiku (~$0.25/M tokens)</option>
                  </select>
                </label>
              </div>
              <div
                className="grid grid-cols-1 md:grid-cols-2"
                style={{
                  gap: '40px',
                  borderTop: '1px solid #e8e5e1',
                  paddingTop: '20px',
                }}
              >
                <div>
                  <div className="eyebrow">Per-run cost</div>
                  <p className="metric-number" style={{ marginTop: '8px' }}>
                    ${perRunCost.toFixed(2)}
                  </p>
                  <p style={{ fontFamily: '"Space Grotesk", system-ui, sans-serif', fontSize: '13px', color: '#606373', marginTop: '6px' }}>
                    Claude: ~${(perRunCost - 0.02).toFixed(2)} · Compute: ~$0.02
                  </p>
                </div>
                <div>
                  <div className="eyebrow">Monthly estimate</div>
                  <p className="metric-number" style={{ marginTop: '8px' }}>
                    ${monthlyCost.toFixed(2)}
                  </p>
                  <p style={{ fontFamily: '"Space Grotesk", system-ui, sans-serif', fontSize: '13px', color: '#606373', marginTop: '6px' }}>
                    {runsPerWeek}×/week · 4.33 weeks · ${perRunCost.toFixed(2)}/run
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </TabPanel>

      {/* Tab 2: Build Your Own */}
      <TabPanel active={activeTab === 2}>
        <div className="space-y-6">
          <div>
            <p style={{ fontSize: '14px', color: '#1b1e2d', lineHeight: 1.65, maxWidth: '720px' }}>
              Want to run this for your own region? Fork the{' '}
              <a href="https://github.com/jtlevine18/weather-ai-pipeline" target="_blank" rel="noopener" style={{ color: '#2d5b7d', fontWeight: 600 }}>GitHub repo</a>,
              copy the prompt below, and paste it into{' '}
              <a href="https://claude.ai/code" target="_blank" rel="noopener" style={{ color: '#2d5b7d', fontWeight: 600 }}>Claude Code</a>.
              It adapts the full pipeline — data collection, forecasting, crop advisories, farmer profiles, and dashboard — for your geography.
            </p>
          </div>

          {/* Full adaptation prompt with copy button */}
          <div>
            <div style={{ position: 'relative' }}>
              <button
                onClick={() => {
                  const el = document.getElementById('rebuild-prompt')
                  if (el) {
                    navigator.clipboard.writeText(el.textContent ?? '').then(() => {
                      const btn = document.getElementById('copy-btn')
                      if (btn) { btn.textContent = 'Copied!'; setTimeout(() => { btn.textContent = 'Copy prompt' }, 2000) }
                    })
                  }
                }}
                id="copy-btn"
                style={{
                  position: 'sticky', top: '8px', float: 'right', zIndex: 1,
                  background: '#fcfaf7', color: '#1b1e2d', border: '1px solid #e8e5e1', borderRadius: '4px',
                  padding: '8px 18px', fontSize: '13px', fontWeight: 600, cursor: 'pointer',
                  fontFamily: '"Space Grotesk", system-ui, sans-serif',
                  marginRight: '10px', marginTop: '10px',
                }}
              >
                Copy prompt
              </button>
              <pre id="rebuild-prompt" style={{
                background: '#fcfaf7', color: '#1b1e2d', borderRadius: '4px',
                border: '1px solid #e8e5e1',
                padding: '24px', fontSize: '12px', lineHeight: 1.7,
                overflow: 'auto', whiteSpace: 'pre-wrap', maxHeight: '600px',
                fontFamily: '"Space Grotesk", system-ui, sans-serif',
              }}>
{`I forked https://github.com/jtlevine18/weather-ai-pipeline — an AI weather forecasting and crop advisory pipeline. I want to adapt it for my region. Read CLAUDE.md to understand the full architecture, then make all the changes below.

=== MY REGION ===

Region name: [e.g. "Central Mexico", "East Africa", "Northern France"]
States/provinces: [e.g. "Jalisco, Michoacán, Guanajuato"]
Timezone: [e.g. "America/Mexico_City", "Africa/Nairobi", "Europe/Paris"]
Language(s) for advisories: [e.g. "es" for Spanish, "sw" for Swahili, "fr" for French]
Currency symbol: [e.g. "$", "KSh", "€"]
Locale code: [e.g. "es-MX", "en-KE", "fr-FR"]

=== MY STATIONS (5-20) ===

1. [City], lat: [XX.XX], lon: [XX.XX], altitude: [XXm], state/province: [Name], crops: [crop1, crop2, crop3]
2. [City], lat: [XX.XX], lon: [XX.XX], altitude: [XXm], state/province: [Name], crops: [crop1, crop2, crop3]
... (add more)

=== MY DATA SOURCE ===

[Describe your weather data source. Options:
- "I have my own API at [endpoint] that returns [format]"
- "I have CSV files with columns [list columns]"
- "Use Open-Meteo current conditions (free, global, no API key)"
- "I want to use [NOAA / Bureau of Meteorology / ECMWF / other]"
- "I'll use synthetic data for now, just set up the pipeline structure"]

=== WHAT TO CHANGE ===

Make ALL of the following changes. This is a 6-step weather pipeline that ingests station data, heals anomalies, generates forecasts, downscales to farmer GPS, produces crop advisories, and delivers via SMS. The reference implementation is for Southern India (Kerala & Tamil Nadu). You are adapting it for my region.

--- 1. STATIONS (config layer) ---

Generate stations.json in the project root with my stations. Format:
[{"station_id": "[XX_CCC]", "name": "[City]", "lat": X, "lon": X, "altitude_m": X, "state": "[State]", "crop_context": "[crops]", "language": "[ISO 639-1]", "imd_id": ""}]

Update _HARDCODED_STATIONS in config.py to match. Copy \`.env.example\` to \`.env\` and set REGION_NAME and TIMEZONE.

--- 2. DATA INGESTION (src/ingestion.py) ---

Write a custom async ingestion function for my data source:
  async def my_fetch(station: StationConfig) -> dict:
      return {"temperature": float, "humidity": float, "wind_speed": float, "pressure": float, "rainfall": float}

Register it at runtime where PipelineConfig is instantiated (see run_pipeline.py, which already does config = get_config(); config.weather.ingestion_source = args.source). Import your my_fetch and assign both fields on the config instance before calling WeatherPipeline(config, ...): config.weather.ingestion_source = "custom"; config.weather.custom_ingest_fn = my_fetch.

If using Open-Meteo: write a function calling the Open-Meteo current weather API for each station's lat/lon.

--- 3. FARMER PROFILES (src/dpi/simulator.py) ---

Generate farmers.json with realistic demo profiles for my stations:
{"[station_id]": {"district": "...", "state": "...", "lang": "...", "crops": [...], "soil": [...], "irrigation": [...], "area": [min, max], "pH": [min, max], "names": [["Name", "Local Script Name"]], "count": 2}}

Use realistic names, crops, soil types, and farm sizes for my region.

--- 4. CROP ADVISORIES (src/translation/curated_advisories.py) ---

Replace the ADVISORY_MATRIX with crop-specific advisories for MY region. Structure:
ADVISORY_MATRIX = {"heavy_rain": {"crop_name": "2-4 sentence advisory...", "default": "..."}, "moderate_rain": {...}, "heat_stress": {...}, "drought_risk": {...}, "frost_risk": {...}, "high_wind": {...}, "foggy": {...}, "clear": {...}, "cyclone_risk": {...}}

Write advisories for every crop in my stations' crop_context fields. Include specific pest/disease risks, irrigation, harvest timing, fertilizer guidance.

--- 5. SEASONAL CONTEXT (src/healing.py) ---

Replace SEASONAL_CONTEXT (currently Kerala/TN × 12 months) with my region:
SEASONAL_CONTEXT = {("[State]", month): {"season": "...", "weather": "temp ranges, rainfall", "crops": "what's growing"}, ...}

Create entries for each state × 12 months. Update the SYSTEM_PROMPT_TEMPLATE to reference my region.

--- 6. DASHBOARD (frontend/src/regionConfig.ts) ---

Replace the REGION object: name, states, languages, dataSource, sourceLabels, locale, currency, timezoneLabel, sidebarFooter, farmerServices. See the file for field descriptions.

--- 7. DOCUMENTATION ---

Update CLAUDE.md title, vision, station list, and architecture to reference my region and data source.

--- 8. VERIFICATION ---

Run: python run_pipeline.py
If it fails, debug and fix. Common issues: DATABASE_URL missing, API keys missing, custom ingestion function errors.

=== WHAT NOT TO CHANGE ===

These are globally portable: src/forecasting.py, src/weather_clients.py, src/downscaling/, src/translation/rag_provider.py, src/delivery/, src/database/, src/pipeline.py, src/models.py, src/api.py, dagster_pipeline/`}
              </pre>
            </div>
          </div>

        </div>
      </TabPanel>
    </div>
  )
}
