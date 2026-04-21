type Props = {
  rain_prob_5mm?: number | null
  rainfall?: number | null
  rain_p50?: number | null
}

// Map a rainfall amount (mm) to an intensity qualifier — same buckets as
// the Python helper in src/translation/prompt_helpers.py.
function intensity(mm: number | null | undefined): string | null {
  if (mm === null || mm === undefined) return null
  if (mm >= 10) return 'heavy'
  if (mm >= 2.5) return 'moderate'
  return 'light'
}

function phrase(
  rain_prob_5mm: number | null | undefined,
  rainfall: number | null | undefined,
  rain_p50: number | null | undefined,
): string {
  if (rain_prob_5mm === null || rain_prob_5mm === undefined) {
    const amount = rainfall ?? 0
    if (amount >= 5) return `likely ${intensity(amount)} rain`
    if (amount >= 1) return `possible ${intensity(amount)} rain`
    return 'mostly dry'
  }
  const q = intensity(rain_p50)
  if (rain_prob_5mm >= 0.6) return q ? `likely ${q} rain` : 'likely rain'
  if (rain_prob_5mm >= 0.3) return q ? `possible ${q} rain` : 'possible rain'
  return 'mostly dry'
}

export function ProbabilityChip({ rain_prob_5mm, rainfall, rain_p50 }: Props) {
  const text = phrase(rain_prob_5mm, rainfall, rain_p50)
  return (
    <span
      style={{
        display: 'inline-block',
        padding: '2px 8px',
        marginTop: '6px',
        fontFamily: '"Space Grotesk", system-ui, sans-serif',
        fontSize: '11px',
        lineHeight: '16px',
        color: '#606373',
        background: '#faf7f1',
        border: '1px solid #e8e5e1',
        borderRadius: '999px',
        whiteSpace: 'nowrap',
      }}
    >
      {text}
    </span>
  )
}
