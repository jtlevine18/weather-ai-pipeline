import type { Step } from 'react-joyride'

export const tourSteps: Step[] = [
  // ── Dashboard ──
  {
    target: '[data-tour="hero"]',
    title: 'Welcome to the AI Weather Pipeline',
    content: 'This dashboard shows an AI weather pipeline that processes real data from 20 Indian meteorological stations every week. Explore the three stages below to see how raw observations become ML-corrected forecasts and bilingual farming advisories — all for about $3/month.',
    placement: 'bottom',
    disableBeacon: true,
  },
  {
    target: '[data-tour="stage-cards"]',
    title: 'Three stages',
    content: 'Raw weather data flows through three stages — collection, forecasting, and advisory generation. Each card links to a deeper view. Let\'s walk through them.',
    placement: 'bottom',
    disableBeacon: true,
  },

  // ── Stations ──
  {
    target: '[data-tour="stations-title"]',
    title: 'Real station data',
    content: 'It starts with live observations from 20 IMD weather stations across Kerala and Tamil Nadu. Ground-truth weather data in most of the world is patchy, delayed, and full of sensor errors — this is no exception.',
    placement: 'bottom',
    disableBeacon: true,
  },
  {
    target: '[data-tour="stations-metrics"]',
    title: 'Quality at a glance',
    content: 'These metrics show what came in and how clean it is. The quality score reflects how much the AI healer had to intervene.',
    placement: 'bottom',
    disableBeacon: true,
  },
  {
    target: '[data-tour="stations-tabs"]',
    title: 'AI-powered data healing',
    content: 'A Claude agent with 5 diagnostic tools cross-validates every reading against neighboring stations, historical norms, and Tomorrow.io satellite data. It catches sensor faults, typos, and drift — then repairs them automatically. For a national met service or agricultural extension program, this replaces manual QA that typically takes days.',
    placement: 'bottom',
    disableBeacon: true,
  },

  // ── Forecasts ──
  {
    target: '[data-tour="forecasts-title"]',
    title: 'Neural weather forecasting',
    content: 'Clean data feeds into NeuralGCM — Google DeepMind\'s neural weather model. Until recently, running a model like this required institutional infrastructure. Now a single person can generate 7-day forecasts for any region on earth.',
    placement: 'bottom',
    disableBeacon: true,
  },
  {
    target: '[data-tour="forecasts-metrics"]',
    title: 'ML bias correction',
    content: 'An XGBoost model trained on local observations corrects systematic biases in the raw forecasts. Confidence scores track how much to trust each prediction. This is the kind of post-processing that national weather services do — automated here.',
    placement: 'bottom',
    disableBeacon: true,
  },
  {
    target: '[data-tour="forecasts-tabs"]',
    title: 'Personalized to each farm',
    content: 'The Downscaling tab shows how station-level forecasts get adjusted to each farmer\'s GPS coordinates using NASA satellite grids and elevation correction. For insurers, ag-input companies, or extension services — this is farm-level weather without farm-level infrastructure.',
    placement: 'top',
    disableBeacon: true,
  },

  // ── Advisories ──
  {
    target: '[data-tour="advisories-title"]',
    title: 'From forecast to advice',
    content: 'This is where it gets interesting. Personalized weather advice has always been expensive — it requires agronomists who understand both meteorology and local farming practices. RAG + LLMs make it possible to generate crop-specific, language-native advice at scale.',
    placement: 'bottom',
    disableBeacon: true,
  },
  {
    target: '[data-tour="advisories-metrics"]',
    title: 'Bilingual delivery',
    content: 'Advisories are generated in Tamil and Malayalam with English translations. The same pattern works for any language pair — the advisory corpus is the part you customize, not the pipeline.',
    placement: 'bottom',
    disableBeacon: true,
  },
  {
    target: '[data-tour="advisories-tabs"]',
    title: 'The last mile',
    content: 'Advisories are delivered by SMS. The Farmer Profiles tab shows how each farmer\'s government records — land, soil health, insurance, credit — are pulled together to personalize advice. This is built on Indian DPI rails, but the architecture works anywhere you have farmer identity data. The real work is socialization — making sure the advice is trusted and actionable.',
    placement: 'top',
    disableBeacon: true,
  },

  // ── Pipeline ──
  {
    target: '[data-tour="pipeline-title"]',
    title: 'Under the hood',
    content: 'This page shows the pipeline architecture, run history, and cost breakdown. Every component has a zero-cost fallback — if the GPU is down, forecasts fall back to Open-Meteo; if Claude is unavailable, a rule-based healer takes over. The whole system is designed to be forked and adapted. This is real data for India, but the real value comes from bringing your own stations, crops, and languages.',
    placement: 'bottom',
    disableBeacon: true,
  },
]

export const stepRoutes: Record<number, string> = {
  0: '/',
  1: '/',
  2: '/stations',
  3: '/stations',
  4: '/stations',
  5: '/forecasts',
  6: '/forecasts',
  7: '/forecasts',
  8: '/advisories',
  9: '/advisories',
  10: '/advisories',
  11: '/pipeline',
}

export const tourStyles = {
  options: {
    zIndex: 10000,
    arrowColor: '#1a1a1a',
    backgroundColor: '#1a1a1a',
    primaryColor: '#d4a019',
    textColor: '#e0dcd5',
    overlayColor: 'rgba(0, 0, 0, 0.45)',
  },
  tooltip: {
    borderRadius: 10,
    padding: '20px 22px',
    maxWidth: 400,
    fontFamily: '"DM Sans", system-ui, sans-serif',
    fontSize: '0.88rem',
    lineHeight: 1.6,
  },
  tooltipTitle: {
    fontFamily: '"Source Serif 4", Georgia, serif',
    fontWeight: 700,
    fontSize: '1.05rem',
    color: '#d4a019',
    marginBottom: 8,
  },
  tooltipContent: {
    padding: '8px 0 0',
  },
  buttonNext: {
    backgroundColor: '#d4a019',
    color: '#fff',
    borderRadius: 6,
    fontFamily: '"DM Sans", system-ui, sans-serif',
    fontWeight: 600,
    fontSize: '0.8rem',
    letterSpacing: '0.5px',
    textTransform: 'uppercase' as const,
    padding: '8px 18px',
  },
  buttonBack: {
    color: '#888',
    fontFamily: '"DM Sans", system-ui, sans-serif',
    fontWeight: 500,
    fontSize: '0.8rem',
    marginRight: 8,
  },
  buttonSkip: {
    color: '#666',
    fontFamily: '"DM Sans", system-ui, sans-serif',
    fontSize: '0.75rem',
  },
  spotlight: {
    borderRadius: 10,
  },
  beacon: {
    display: 'none',
  },
  beaconInner: {
    display: 'none',
  },
  beaconOuter: {
    display: 'none',
  },
}
