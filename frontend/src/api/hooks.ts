import { useQuery } from '@tanstack/react-query'
import { apiFetch } from './client'
import {
  STATIONS_VIEW,
  TELEMETRY_RAW,
  TELEMETRY_CLEAN,
  FORECASTS,
  ALERTS,
  DELIVERIES,
  HEALING_RECORDS,
  HEALING_STATS,
  PIPELINE_RUNS,
  PIPELINE_STATS,
  SOURCES,
  MOS_STATUS,
  EVAL_METRICS,
  CONVERSATION_LOG,
  DELIVERY_METRICS_AGG,
  FARMERS_SUMMARY,
} from './mockData'

// ── Types ──────────────────────────────────────────────────

// Matches reskin/original api/stations.ts hardcoded stub shape
// (no `stations` table exists in the DB schema)
export interface Station {
  id: string
  name: string
  state: string
  lat: number
  lon: number
  altitude_m?: number
  // Not in the stub but tolerated by components — `source` and `active`
  // are still referenced in the mock; they'll be undefined when port chat
  // switches to the real endpoint unless/until it enriches the response.
  source?: string
  active?: boolean
}

// Matches DB `forecasts` table columns
export interface Forecast {
  id?: string | number
  station_id: string
  // Derived frontend-only, filled from stationMap fallback where used
  station_name?: string
  issued_at?: string
  valid_for_ts?: string
  forecast_day?: number
  temperature?: number
  humidity?: number
  wind_speed?: number
  rainfall?: number
  condition?: string
  model_used?: string
  nwp_source?: string
  nwp_temp?: number
  correction?: number
  confidence?: number
  created_at?: string
  // Frontend-only derived fields (NOT in DB) — components use them for
  // day-level min/max display. Port chat will need to compute these or
  // switch the UI to the single `temperature` field.
  temp_min?: number
  temp_max?: number
}

// Matches DB `agricultural_alerts` table columns
export interface Alert {
  id?: string | number
  station_id: string
  // Derived frontend-only
  station_name?: string
  farmer_lat?: number
  farmer_lon?: number
  issued_at?: string
  condition?: string
  advisory_en?: string
  advisory_local?: string
  sms_en?: string
  sms_local?: string
  language?: string
  provider?: string
  retrieval_docs?: number
  forecast_days?: number
  created_at?: string
  // Frontend-only — no `severity` column in DB; port chat may compute from
  // `condition` or drop the filter.
  severity?: string
}

// NOTE: No backend endpoint exists for station-latest. Shape kept as-is;
// the port chat will need to stand one up (e.g. by joining stations with
// the latest clean_telemetry row) and decide on the final field names.
export interface StationLatest {
  station_id: string
  station_name?: string
  state?: string
  latitude?: number
  longitude?: number
  temperature?: number
  humidity?: number
  rainfall_mm?: number
  wind_speed?: number
  quality_score?: number
  observed_at?: string
  source?: string
}

// Matches DB `pipeline_runs` table columns
export interface PipelineRun {
  id?: string | number
  started_at?: string
  ended_at?: string
  status?: string
  steps_ok?: number
  steps_fail?: number
  summary?: string
  // Frontend-only fields that the DB schema does NOT currently contain.
  // The port chat will either need to add columns, compute them from
  // related tables, or remove these from the UI.
  run_id?: string
  duration_seconds?: number
  stations_processed?: number
  records_ingested?: number
  errors?: number
  error_detail?: string
}

// Matches DB `raw_telemetry` / `clean_telemetry` table columns
export interface TelemetryRecord {
  id?: string | number
  station_id: string
  // Derived frontend-only
  station_name?: string
  ts?: string
  temperature?: number
  humidity?: number
  wind_speed?: number
  wind_dir?: number
  pressure?: number
  rainfall?: number
  quality_score?: number
  source?: string
  fault_type?: string
  heal_action?: string
  heal_source?: string
  created_at?: string
  // Frontend-only derived field; not in DB.
  fields_filled?: number
}

// Matches DB `delivery_log` table columns
export interface DeliveryRecord {
  id?: string | number
  alert_id?: string
  station_id?: string
  // Derived frontend-only
  station_name?: string
  channel?: string
  recipient?: string
  status?: string
  message?: string
  sms_text?: string
  delivered_at?: string
  // Not in DB — kept so `d.created_at` references continue to type-check.
  created_at?: string
}

export interface HealingRecord {
  id?: string
  pipeline_run_id?: string
  reading_id?: string
  station_id?: string
  assessment?: string
  reasoning?: string
  corrections?: string
  quality_score?: number
  tools_used?: string
  original_values?: string
  model?: string
  tokens_in?: number
  tokens_out?: number
  latency_s?: number
  fallback_used?: boolean
  created_at?: string
  // Legacy fields (kept for compatibility)
  field?: string
  original_value?: string | number | null
  healed_value?: string | number | null
  method?: string
  healed_at?: string
}

export interface HealingStats {
  total_healed?: number
  by_field?: Record<string, number>
  by_method?: Record<string, number>
  recent_count?: number
  assessment_distribution?: Record<
    string,
    { count: number; avg_quality?: number | null }
  >
  latest_run?: {
    model?: string
    tokens_in?: number
    tokens_out?: number
    latency_s?: number
    fallback_used?: boolean
  }
}

// API returns raw table counts: {raw_telemetry: 300, forecasts: 1092, ...}
export interface PipelineStats {
  raw_telemetry?: number
  clean_telemetry?: number
  healing_log?: number
  forecasts?: number
  agricultural_alerts?: number
  delivery_log?: number
  pipeline_runs?: number
  // Legacy fields (kept for components that reference them)
  total_runs?: number
  successful_runs?: number
  failed_runs?: number
  avg_duration?: number
  last_run?: PipelineRun
  total_records?: number
}

// API returns: [{source: "imd", count: 210}, {source: "imdlib", count: 90}]
export interface SourceInfo {
  source?: string
  count?: number
  // Legacy fields
  name: string
  type?: string
  stations?: number
  last_fetch?: string
  status?: string
}

// ── Mock delay helper ──────────────────────────────────────
// Simulates a fast network request so React Query still treats
// these as real async sources (isLoading, caching, etc. all work).

function mock<T>(value: T, delayMs = 260): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), delayMs))
}

// ── Hooks ──────────────────────────────────────────────────

export function useStations() {
  return useQuery<Station[]>({
    queryKey: ['stations'],
    queryFn: () => apiFetch<Station[]>('/api/stations'),
    staleTime: 5 * 60 * 1000,
  })
}

export function useForecasts(limit = 50, forecastDay?: number) {
  const params = new URLSearchParams({ limit: String(limit) })
  if (forecastDay !== undefined) params.set('forecast_day', String(forecastDay))
  return useQuery<Forecast[]>({
    queryKey: ['forecasts', limit, forecastDay],
    queryFn: () => apiFetch<Forecast[]>(`/api/forecasts?${params}`),
  })
}

export function useAlerts(limit = 50) {
  return useQuery<Alert[]>({
    queryKey: ['alerts', limit],
    queryFn: () => apiFetch<Alert[]>(`/api/alerts?limit=${limit}`),
  })
}

export function useStationLatest(stationId: string) {
  return useQuery<StationLatest>({
    queryKey: ['station-latest', stationId],
    queryFn: () => apiFetch<StationLatest>(`/api/stations?id=${encodeURIComponent(stationId)}`),
    enabled: !!stationId,
  })
}

export function usePipelineRuns(limit = 20) {
  return useQuery<PipelineRun[]>({
    queryKey: ['pipeline-runs', limit],
    queryFn: () => apiFetch<PipelineRun[]>(`/api/pipeline?mode=runs&limit=${limit}`),
  })
}

export function useTelemetryRaw(limit = 50) {
  return useQuery<TelemetryRecord[]>({
    queryKey: ['telemetry-raw', limit],
    queryFn: () => apiFetch<TelemetryRecord[]>(`/api/telemetry?type=raw&limit=${limit}`),
  })
}

export function useTelemetryClean(limit = 50) {
  return useQuery<TelemetryRecord[]>({
    queryKey: ['telemetry-clean', limit],
    queryFn: () => apiFetch<TelemetryRecord[]>(`/api/telemetry?type=clean&limit=${limit}`),
  })
}

export function useDeliveryLog(limit = 50) {
  return useQuery<DeliveryRecord[]>({
    queryKey: ['delivery-log', limit],
    queryFn: () => apiFetch<DeliveryRecord[]>(`/api/delivery?mode=log&limit=${limit}`),
  })
}

export function useHealingLog(limit = 50) {
  return useQuery<HealingRecord[]>({
    queryKey: ['healing-log', limit],
    queryFn: () => apiFetch<HealingRecord[]>(`/api/healing?mode=log&limit=${limit}`),
  })
}

export function useHealingStats() {
  return useQuery<HealingStats>({
    queryKey: ['healing-stats'],
    queryFn: () => apiFetch<HealingStats>('/api/healing?mode=stats'),
  })
}

export function usePipelineStats() {
  return useQuery<PipelineStats>({
    queryKey: ['pipeline-stats'],
    queryFn: () => apiFetch<PipelineStats>('/api/pipeline?mode=stats'),
  })
}

export function useSources() {
  return useQuery<SourceInfo[]>({
    queryKey: ['sources'],
    queryFn: async () => {
      const raw = await apiFetch<Array<{ source?: string; name?: string; count?: number; type?: string; stations?: number; status?: string }>>('/api/sources')
      return raw.map((s) => ({
        name: s.source ?? s.name ?? 'Unknown',
        source: s.source,
        count: s.count,
        type: s.type,
        stations: s.stations ?? s.count,
        status: s.status,
      }))
    },
    staleTime: 5 * 60 * 1000,
  })
}

export function useEvals() {
  return useQuery<Record<string, any>>({
    queryKey: ['evals'],
    queryFn: () => apiFetch<Record<string, any>>('/api/metrics'),
    staleTime: 5 * 60 * 1000,
  })
}

export function useConversationLog(limit = 50) {
  return useQuery<any[]>({
    queryKey: ['conversation-log', limit],
    queryFn: () => apiFetch<any[]>(`/api/conversation?limit=${limit}`),
  })
}

export function useDeliveryMetricsAgg(limit = 200) {
  return useQuery<any[]>({
    queryKey: ['delivery-metrics', limit],
    queryFn: () => apiFetch<any[]>(`/api/delivery?mode=metrics&limit=${limit}`),
  })
}

// ── Farmer / DPI ──────────────────────────────────────────

// Matches DB `farmer_profiles` table columns (with the caveat that
// `primary_crops` is stored as VARCHAR in the DB — the port chat will
// need to parse it to an array on the way out, or the backend can split
// before returning).
export interface FarmerSummary {
  phone: string
  name: string
  district: string
  station_id: string
  primary_crops: string[]
  total_area: number
}

export interface FarmerDetail {
  aadhaar: { name: string; name_local: string; phone: string; district: string; state: string; language: string }
  primary_crops: string[]
  total_area: number
  land_records: { survey_number: string; area_hectares: number; soil_type: string; irrigation_type: string; gps_lat: number; gps_lon: number }[]
  soil_health?: { pH: number; classification: string; nitrogen_kg_ha: number; phosphorus_kg_ha: number; potassium_kg_ha: number; organic_carbon_pct: number } | null
  pmkisan?: { installments_received: number; total_amount: number } | null
  pmfby?: { status: string; sum_insured: number; premium_paid: number } | null
  kcc?: { credit_limit: number; outstanding: number; repayment_status: string } | null
}

export function useFarmers(opts?: { enabled?: boolean }) {
  return useQuery<FarmerSummary[]>({
    queryKey: ['farmers'],
    queryFn: () => apiFetch<FarmerSummary[]>('/api/farmers'),
    staleTime: 5 * 60 * 1000,
    enabled: opts?.enabled ?? true,
  })
}

export function useFarmerDetail(phone: string) {
  return useQuery<FarmerDetail>({
    queryKey: ['farmer-detail', phone],
    queryFn: () => apiFetch<FarmerDetail>(`/api/farmers?phone=${encodeURIComponent(phone)}`),
    enabled: !!phone,
  })
}

// ── MOS Model Status ──────────────────────────────────────

export interface MosStatus {
  trained: boolean
  metrics: {
    rmse?: number
    mae?: number
    r2?: number
    n_train?: number
    n_test?: number
    residual_mean?: number
    residual_std?: number
    feature_importances?: Record<string, number>
  } | null
}

export function useMosStatus() {
  return useQuery<MosStatus>({
    queryKey: ['mos-status'],
    queryFn: () => apiFetch<MosStatus>('/api/pipeline?mode=mos-status'),
    staleTime: 30_000,
  })
}
