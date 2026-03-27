/**
 * Region configuration — all geography-specific strings in one place.
 *
 * To adapt this dashboard for a different region, edit only this file.
 * Everything else in the frontend pulls from here.
 *
 * See REBUILD.md for a full example adapted for Central Mexico.
 */

export const REGION = {
  /** Display name for the region (used in hero text, descriptions) */
  name: 'Southern India',

  /** States or provinces covered (used in filters, descriptions, sidebar) */
  states: ['Kerala', 'Tamil Nadu'],

  /**
   * Languages used for advisories.
   * Keys = ISO 639-1 codes (must match the `language` field in stations.json).
   * Values = display names shown in the UI.
   */
  languages: { ta: 'Tamil', ml: 'Malayalam' } as Record<string, string>,

  /** Joined for prose: "Tamil and Malayalam" */
  get languageList(): string {
    return Object.values(this.languages).join(' and ')
  },

  /** Joined for metric cards: "Tamil / Malayalam" */
  get languageMetric(): string {
    return Object.values(this.languages).join(' / ')
  },

  /** Name of your primary data source (shown in descriptions and badges) */
  dataSource: 'IMD',

  /**
   * Badge labels for data source types in the Stations page.
   * Keys must match the `source` field written by your ingestion function
   * into the raw_telemetry table. Values = [display label, color hex].
   */
  sourceLabels: {
    imd_api: ['India Met Dept', '#2E7D32'],
    imdlib: ['IMD Gridded Archive', '#1565C0'],
    synthetic: ['Synthetic', '#888'],
    custom: ['Custom', '#6B5B95'],
  } as Record<string, [string, string]>,

  /** Locale for date and number formatting (e.g. "en-IN", "es-MX", "fr-FR") */
  locale: 'en-IN',

  /** Currency symbol for financial displays in farmer profiles */
  currency: 'Rs',

  /** Timezone abbreviation shown in the scheduler description */
  timezoneLabel: 'IST',

  /** Text shown at the bottom of the sidebar */
  sidebarFooter: 'Kerala \u00B7 Tamil Nadu',

  /**
   * Display labels for farmer service cards in the Advisories page.
   * These map to India's Digital Public Infrastructure programs by default.
   * Change the labels to your country's equivalents — keep the keys the same
   * since the React components use them to render the right cards.
   *
   * pmkisan = income support / subsidy program
   * pmfby   = crop insurance program
   * kcc     = farm credit / loan facility
   * soil    = soil testing / health card
   */
  farmerServices: {
    pmkisan: 'PM-KISAN',
    pmfby: 'PMFBY Crop Insurance',
    kcc: 'Kisan Credit Card',
    soil: 'Soil Health Card',
  },
}

/** Resolve a language code to its display name, falling back to the code itself */
export function languageName(code: string): string {
  return REGION.languages[code] ?? code
}
