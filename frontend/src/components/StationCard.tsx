import { Link } from 'react-router-dom'
import { MapPin, Thermometer } from 'lucide-react'
import type { Station } from '../api/hooks'

interface Props {
  station: Station
  latestTemp?: number | null
}

export function StationCard({ station, latestTemp }: Props) {
  return (
    <Link
      to={`/stations/${station.station_id}`}
      className="card card-body group hover:border-primary-300 hover:shadow-md transition-all duration-150"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <h3 className="font-semibold text-slate-900 truncate group-hover:text-primary-700 transition-colors">
            {station.name}
          </h3>
          <p className="text-sm text-slate-500 mt-0.5">{station.state}</p>
        </div>
        {latestTemp !== null && latestTemp !== undefined && (
          <div className="flex items-center gap-1 text-slate-600 shrink-0">
            <Thermometer size={16} className="text-amber-500" />
            <span className="text-lg font-semibold">{latestTemp.toFixed(1)}&deg;</span>
          </div>
        )}
      </div>
      <div className="flex items-center gap-1.5 mt-3 text-xs text-slate-400">
        <MapPin size={12} />
        <span>
          {station.latitude.toFixed(2)}, {station.longitude.toFixed(2)}
        </span>
        {station.source && (
          <>
            <span className="mx-1">|</span>
            <span>{station.source}</span>
          </>
        )}
      </div>
    </Link>
  )
}
