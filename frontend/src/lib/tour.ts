import type { Step } from 'react-joyride'

export const tourSteps: Step[] = [
  // ── Dashboard ──
  {
    target: '[data-tour="hero"]',
    title: 'Welcome',
    content: 'This dashboard runs a weather intelligence system for smallholder farmers in Southern India. Every week, it collects real weather data, generates locally accurate forecasts, and sends personalized farming advice by SMS — in Tamil and Malayalam. The whole thing costs about $3/month to run.',
    placement: 'bottom',
    disableBeacon: true,
  },
  {
    target: '[data-tour="stage-cards"]',
    title: 'Three stages',
    content: 'Weather data flows through three stages — collection, forecasting, and advisory generation. Each card links to a deeper view. Let\'s walk through them.',
    placement: 'bottom',
    disableBeacon: true,
  },

  // ── Stations ──
  {
    target: '[data-tour="stations-title"]',
    title: 'Real station data',
    content: 'It starts with live observations from 20 weather stations across Kerala and Tamil Nadu. Ground-truth weather data in most of the world is patchy, delayed, and full of sensor errors — this is no exception.',
    placement: 'bottom',
    disableBeacon: true,
  },
  {
    target: '[data-tour="stations-metrics"]',
    title: 'Data quality',
    content: 'These metrics show what came in and how clean it is. The accuracy score reflects how much the AI had to intervene to fix problems.',
    placement: 'bottom',
    disableBeacon: true,
  },
  {
    target: '[data-tour="stations-tabs"]',
    title: 'Automated data cleaning',
    content: 'Raw data from weather stations is never perfect — sensors fail, readings get corrupted, values drift over time. An AI agent automatically detects these problems by checking against neighboring stations, historical patterns, and satellite data, then fixes them. What would normally take a team days happens in minutes.',
    placement: 'bottom',
    disableBeacon: true,
  },

  // ── Forecasts ──
  {
    target: '[data-tour="forecasts-title"]',
    title: 'AI-powered forecasts',
    content: 'Clean station data feeds into a neural weather model that generates 7-day forecasts for each station. These are the same kind of forecasts that national weather services produce — temperature, rainfall, humidity, wind — now running automatically for 20 stations at near-zero cost.',
    placement: 'bottom',
    disableBeacon: true,
  },
  {
    target: '[data-tour="forecasts-metrics"]',
    title: 'Local accuracy',
    content: 'Raw forecasts are corrected using local weather history — the same technique national weather services use, but automated. Each prediction gets a confidence score so you know how much to trust it.',
    placement: 'bottom',
    disableBeacon: true,
    disableScrolling: true,
  },
  {
    target: '[data-tour="forecasts-tabs"]',
    title: 'Personalized to each farm',
    content: 'Weather stations are spread far apart, but farmers need forecasts for their exact location. The system uses NASA satellite data and altitude adjustments to tailor predictions to each farmer\'s GPS coordinates — farm-level weather without farm-level infrastructure.',
    placement: 'top',
    disableBeacon: true,
    disableScrolling: true,
  },

  // ── Advisories ──
  {
    target: '[data-tour="advisories-title"]',
    title: 'From forecast to advice',
    content: 'Personalized farming advice has always been expensive — it requires agronomists who understand both weather and local crops. Here, each farmer gets specific recommendations for their crops and conditions: when to irrigate, when to harvest, what to spray, when to hold off.',
    placement: 'bottom',
    disableBeacon: true,
  },
  {
    target: '[data-tour="advisories-metrics"]',
    title: 'Bilingual delivery',
    content: 'Advisories are generated in Tamil and Malayalam with English translations. The same approach works for any language — you customize the advisory knowledge base, not the system.',
    placement: 'bottom',
    disableBeacon: true,
    disableScrolling: true,
  },
  {
    target: '[data-tour="advisories-tabs"]',
    title: 'The last mile',
    content: 'Advisories go out by SMS. The Farmer Profiles tab shows how each farmer\'s official records — land ownership, soil tests, crop insurance, credit — are used to personalize the advice they receive. The hard part isn\'t the technology. It\'s building trust so farmers actually act on it.',
    placement: 'top',
    disableBeacon: true,
    disableScrolling: true,
  },

  // ── Pipeline ──
  {
    target: '[data-tour="pipeline-title"]',
    title: 'Under the hood',
    content: 'This page shows the system architecture, run history, and cost breakdown. Every component has a fallback — if one service is down, the system degrades gracefully instead of failing. The whole thing is designed to be adapted: bring your own stations, crops, and languages.',
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
