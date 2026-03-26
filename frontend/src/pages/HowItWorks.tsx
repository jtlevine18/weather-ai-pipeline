import {
  Database,
  Shield,
  CloudSun,
  MapPin,
  Languages,
  Send,
} from 'lucide-react'

/* ── step data ─────────────────────────────────────────── */

interface Step {
  icon: typeof Database
  name: string
  explanation: string
  interesting: string
}

const STEPS: Step[] = [
  {
    icon: Database,
    name: 'Ingest',
    explanation:
      'Every week, we scrape real-time weather data from India\u2019s Meteorological Department for 20 stations across Kerala and Tamil Nadu. When the primary IMD API is down, we fall back to imdlib gridded data, then to Open-Meteo as a last resort. The pipeline always gets data \u2014 it just gets it from the best available source.',
    interesting:
      'Three-level degradation chain ensures zero data loss. Each source is independently tested.',
  },
  {
    icon: Shield,
    name: 'Heal',
    explanation:
      'Raw weather data is messy \u2014 sensors drift, readings go missing, values spike. An AI agent (Claude Sonnet with 5 specialized tools) examines each reading, cross-validates against Tomorrow.io reference data, and decides whether to correct, fill, or flag it. If Claude is unavailable, a rule-based fallback applies the same logic without AI reasoning.',
    interesting:
      'The healer is a genuine AI agent with tools, not just a prompt. It can query station metadata, historical normals, neighboring stations, and seasonal context before making a decision.',
  },
  {
    icon: CloudSun,
    name: 'Forecast',
    explanation:
      'We run Google DeepMind\u2019s NeuralGCM \u2014 the same neural weather model that matches ECMWF accuracy \u2014 on GPU to generate 7-day global forecasts. Then XGBoost MOS (Model Output Statistics) corrects systematic biases using local observation history. When no GPU is available, Open-Meteo provides the NWP baseline.',
    interesting:
      'NeuralGCM runs a single global inference pass and we extract all 20 stations from the output. One forward pass, 20 forecasts.',
  },
  {
    icon: MapPin,
    name: 'Downscale',
    explanation:
      'Station forecasts are too coarse for individual farms. We fetch a 3\u00d73 grid of NASA POWER satellite observations around each station, use Inverse Distance Weighting to interpolate to the farmer\u2019s exact GPS coordinates, then apply a lapse-rate elevation correction (temperature drops ~6.5\u00b0C per 1000m of altitude gain).',
    interesting:
      'A farmer 500m uphill from the station gets a meaningfully different temperature forecast \u2014 this matters for frost-sensitive crops.',
  },
  {
    icon: Languages,
    name: 'Translate',
    explanation:
      'A hybrid RAG system (FAISS dense vectors + BM25 sparse retrieval) finds relevant agricultural knowledge, then Claude generates a crop-specific weekly advisory in English. A separate Claude call translates it to Tamil or Malayalam. If Claude is down, rule-based templates produce the advisory at zero cost.',
    interesting:
      'Three-level fallback: RAG+Claude \u2192 Claude-only \u2192 rule-based templates. The pipeline always produces an advisory.',
  },
  {
    icon: Send,
    name: 'Deliver',
    explanation:
      'Advisories are delivered via SMS to registered farmers. Each advisory includes the 7-day outlook, specific day references (\u2018avoid spraying on Day 3-4\u2019), and crop-specific recommendations.',
    interesting:
      'Currently console-only (dry run). Production delivery uses Twilio SMS + WhatsApp.',
  },
]

/* ── tech stack ────────────────────────────────────────── */

interface TechItem {
  name: string
  role: string
}

const TECH: TechItem[] = [
  { name: 'NeuralGCM', role: 'Google DeepMind neural weather model' },
  { name: 'XGBoost', role: 'ML bias correction (MOS)' },
  { name: 'Claude', role: 'Agentic healing, advisory generation, translation' },
  { name: 'FAISS + BM25', role: 'Hybrid RAG retrieval' },
  { name: 'PostgreSQL', role: 'Production database (Neon hosted)' },
  { name: 'NASA POWER', role: 'Satellite data for spatial downscaling' },
  { name: 'IMD + imdlib', role: 'India Met Dept station observations' },
  { name: 'Open-Meteo', role: 'NWP fallback (GFS/ECMWF)' },
  { name: 'Tomorrow.io', role: 'Cross-validation reference for healing' },
  { name: 'FastAPI', role: 'REST API backend' },
  { name: 'React + Vite', role: 'Dashboard frontend' },
  { name: 'Dagster', role: 'Pipeline orchestration (alternative)' },
]

/* ── component ─────────────────────────────────────────── */

export default function HowItWorks() {
  return (
    <div className="space-y-8">
      {/* Title */}
      <div style={{ padding: '28px 0 0' }}>
        <h1
          style={{
            margin: 0,
            fontWeight: 700,
            color: '#1a1a1a',
            fontFamily: '"Source Serif 4", Georgia, serif',
            letterSpacing: '-0.5px',
            lineHeight: 1.25,
            fontSize: '1.65rem',
          }}
        >
          How It Works
        </h1>
        <p
          style={{
            color: '#888',
            lineHeight: 1.6,
            margin: '6px 0 0',
            fontFamily: '"DM Sans", sans-serif',
            fontSize: '0.86rem',
          }}
        >
          A 6-step pipeline from raw IMD station data to bilingual farming advisories delivered by
          SMS.
        </p>
      </div>

      {/* Steps */}
      {STEPS.map((step, idx) => {
        const Icon = step.icon
        return (
          <div
            key={step.name}
            style={{
              background: '#fff',
              border: '1px solid #e0dcd5',
              borderRadius: '14px',
              padding: '24px',
              fontFamily: '"DM Sans", sans-serif',
            }}
          >
            {/* Step header */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '14px' }}>
              <div
                style={{
                  width: 40,
                  height: 40,
                  borderRadius: '10px',
                  background: 'rgba(212, 160, 25, 0.10)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  flexShrink: 0,
                }}
              >
                <Icon size={20} color="#d4a019" strokeWidth={1.8} />
              </div>
              <div>
                <span
                  style={{
                    fontSize: '0.68rem',
                    fontWeight: 600,
                    textTransform: 'uppercase',
                    letterSpacing: '1.2px',
                    color: '#999',
                  }}
                >
                  Step {idx + 1}
                </span>
                <h2
                  style={{
                    margin: 0,
                    fontSize: '1.15rem',
                    fontWeight: 700,
                    color: '#1a1a1a',
                    fontFamily: '"Source Serif 4", Georgia, serif',
                    lineHeight: 1.3,
                  }}
                >
                  {step.name}
                </h2>
              </div>
            </div>

            {/* Explanation */}
            <p
              style={{
                color: '#555',
                fontSize: '0.86rem',
                lineHeight: 1.7,
                margin: '0 0 16px',
              }}
            >
              {step.explanation}
            </p>

            {/* Interesting callout */}
            <div
              style={{
                borderLeft: '3px solid #d4a019',
                padding: '12px 16px',
                background: 'rgba(212, 160, 25, 0.04)',
                borderRadius: '0 8px 8px 0',
              }}
            >
              <div
                style={{
                  fontSize: '0.7rem',
                  fontWeight: 600,
                  textTransform: 'uppercase',
                  letterSpacing: '1px',
                  color: '#d4a019',
                  marginBottom: '4px',
                }}
              >
                What makes this interesting
              </div>
              <p
                style={{
                  color: '#555',
                  fontSize: '0.82rem',
                  lineHeight: 1.6,
                  margin: 0,
                }}
              >
                {step.interesting}
              </p>
            </div>
          </div>
        )
      })}

      {/* Tech Stack */}
      <div>
        <div
          style={{
            fontFamily: '"DM Sans", sans-serif',
            fontSize: '0.72rem',
            fontWeight: 600,
            textTransform: 'uppercase',
            letterSpacing: '1.5px',
            color: '#888',
            paddingBottom: '8px',
            marginBottom: '16px',
            borderBottom: '2px solid #d4a019',
          }}
        >
          Tech Stack
        </div>

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
            gap: '12px',
          }}
        >
          {TECH.map((t) => (
            <div
              key={t.name}
              style={{
                background: '#fff',
                border: '1px solid #e0dcd5',
                borderRadius: '10px',
                padding: '14px 16px',
                fontFamily: '"DM Sans", sans-serif',
              }}
            >
              <div style={{ fontWeight: 600, fontSize: '0.88rem', color: '#1a1a1a' }}>
                {t.name}
              </div>
              <div style={{ color: '#888', fontSize: '0.75rem', lineHeight: 1.45, marginTop: 4 }}>
                {t.role}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
