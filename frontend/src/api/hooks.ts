import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from './client'

// ── Types ──────────────────────────────────────────────────

export interface Station {
  station_id: string
  name: string
  state: string
  latitude: number
  longitude: number
  elevation?: number
  source?: string
  active?: boolean
}

export interface Forecast {
  id?: number
  station_id: string
  station_name?: string
  forecast_date?: string
  forecast_day?: number
  temp_min?: number
  temp_max?: number
  rainfall_mm?: number
  humidity?: number
  condition?: string
  model?: string
  model_used?: string
  confidence?: number
  created_at?: string
}

export interface Alert {
  id?: number
  station_id: string
  station_name?: string
  condition?: string
  severity?: string
  advisory_en?: string
  advisory_local?: string
  language?: string
  issued_at?: string
  created_at?: string
}

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

export interface PipelineRun {
  id?: number
  run_id?: string
  status?: string
  started_at?: string
  finished_at?: string
  duration_seconds?: number
  stations_processed?: number
  records_ingested?: number
  errors?: number
  error_detail?: string
}

export interface TelemetryRecord {
  id?: number
  station_id: string
  station_name?: string
  temperature?: number
  humidity?: number
  rainfall_mm?: number
  wind_speed?: number
  observed_at?: string
  quality_score?: number
  source?: string
  heal_action?: string
  fields_filled?: number
}

export interface DeliveryRecord {
  id?: number
  station_id?: string
  station_name?: string
  channel?: string
  recipient?: string
  status?: string
  message_preview?: string
  delivered_at?: string
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

// ── Hooks ──────────────────────────────────────────────────

export function useStations() {
  return useQuery<Station[]>({
    queryKey: ['stations'],
    queryFn: async () => {
      const raw: any[] = await apiFetch('/api/stations')
      return raw.map((s) => ({
        station_id: s.station_id ?? s.id ?? '',
        name: s.name ?? '',
        state: s.state ?? '',
        latitude: s.latitude ?? s.lat ?? 0,
        longitude: s.longitude ?? s.lon ?? 0,
        elevation: s.elevation ?? s.altitude_m,
        source: s.source,
        active: s.active,
      }))
    },
    staleTime: 5 * 60 * 1000,
  })
}

export function useForecasts(limit = 50, forecastDay?: number) {
  const params = new URLSearchParams({ limit: String(limit) })
  if (forecastDay !== undefined) params.set('forecast_day', String(forecastDay))

  return useQuery<Forecast[]>({
    queryKey: ['forecasts', limit, forecastDay],
    queryFn: () => apiFetch(`/api/forecasts?${params}`),
  })
}

export function useAlerts(limit = 50) {
  return useQuery<Alert[]>({
    queryKey: ['alerts', limit],
    queryFn: () => apiFetch(`/api/alerts?limit=${limit}`),
  })
}

export function useStationLatest(stationId: string) {
  return useQuery<StationLatest>({
    queryKey: ['station-latest', stationId],
    queryFn: () => apiFetch(`/api/station/${stationId}/latest`),
    enabled: !!stationId,
  })
}

export function usePipelineRuns(limit = 20) {
  return useQuery<PipelineRun[]>({
    queryKey: ['pipeline-runs', limit],
    queryFn: () => apiFetch(`/api/pipeline/runs?limit=${limit}`),
  })
}

function normalizeTelemetry(raw: any[]): TelemetryRecord[] {
  return raw.map((r) => ({
    ...r,
    observed_at: r.observed_at ?? r.ts ?? '',
    rainfall_mm: r.rainfall_mm ?? r.rainfall,
    heal_action: r.heal_action ?? undefined,
    fields_filled: r.fields_filled ?? undefined,
  }))
}

export function useTelemetryRaw(limit = 50) {
  return useQuery<TelemetryRecord[]>({
    queryKey: ['telemetry-raw', limit],
    queryFn: async () => {
      const data: any[] = await apiFetch(`/api/telemetry/raw?limit=${limit}`)
      return normalizeTelemetry(data)
    },
  })
}

export function useTelemetryClean(limit = 50) {
  return useQuery<TelemetryRecord[]>({
    queryKey: ['telemetry-clean', limit],
    queryFn: async () => {
      const data: any[] = await apiFetch(`/api/telemetry/clean?limit=${limit}`)
      return normalizeTelemetry(data)
    },
  })
}

export function useDeliveryLog(limit = 50) {
  return useQuery<DeliveryRecord[]>({
    queryKey: ['delivery-log', limit],
    queryFn: () => apiFetch(`/api/delivery/log?limit=${limit}`),
  })
}

export function useHealingLog(limit = 50) {
  return useQuery<HealingRecord[]>({
    queryKey: ['healing-log', limit],
    queryFn: () => apiFetch(`/api/healing/log?limit=${limit}`),
  })
}

export function useHealingStats() {
  return useQuery<HealingStats>({
    queryKey: ['healing-stats'],
    queryFn: () => apiFetch('/api/healing/stats'),
  })
}

export function usePipelineStats() {
  return useQuery<PipelineStats>({
    queryKey: ['pipeline-stats'],
    queryFn: () => apiFetch('/api/pipeline/stats'),
  })
}

export function useSources() {
  return useQuery<SourceInfo[]>({
    queryKey: ['sources'],
    queryFn: async () => {
      const raw: any[] = await apiFetch('/api/sources')
      // API returns [{source: "imd", count: 210}] — normalize to SourceInfo
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
    queryFn: () => apiFetch('/api/evals'),
    staleTime: 5 * 60 * 1000,
  })
}

export function useConversationLog(limit = 50) {
  return useQuery<any[]>({
    queryKey: ['conversation-log', limit],
    queryFn: () => apiFetch(`/api/conversation/log?limit=${limit}`),
  })
}

export function useDeliveryMetricsAgg(limit = 200) {
  return useQuery<any[]>({
    queryKey: ['delivery-metrics', limit],
    queryFn: () => apiFetch(`/api/delivery/metrics?limit=${limit}`),
  })
}

// ── Farmer / DPI ──────────────────────────────────────────

export interface FarmerSummary {
  phone: string
  name: string
  district: string
  station: string
  crops: string[]
  area_ha: number
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
    queryFn: () => apiFetch('/api/farmers'),
    staleTime: 5 * 60 * 1000,
    enabled: opts?.enabled ?? true,
  })
}

export function useFarmerDetail(phone: string) {
  return useQuery<FarmerDetail>({
    queryKey: ['farmer-detail', phone],
    queryFn: () => apiFetch(`/api/farmers/${encodeURIComponent(phone)}`),
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
    queryFn: () => apiFetch('/api/pipeline/mos-status'),
    staleTime: 30_000,
  })
}

// ── Pipeline Actions (mutations) ──────────────────────────

export function useTriggerPipeline() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => apiFetch<{ status: string; run_id?: string }>('/api/pipeline/trigger', { method: 'POST' }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['pipeline-runs'] })
      qc.invalidateQueries({ queryKey: ['pipeline-stats'] })
    },
  })
}

export function useRetrainMos() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => apiFetch<{ status: string }>('/api/pipeline/retrain-mos', { method: 'POST' }),
    onSuccess: () => {
      // Invalidate after a delay to give the background job time to finish
      setTimeout(() => qc.invalidateQueries({ queryKey: ['mos-status'] }), 5000)
    },
  })
}
