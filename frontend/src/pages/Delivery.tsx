import { useDeliveryLog } from '../api/hooks'
import { StatusBadge } from '../components/StatusBadge'
import { PageLoader } from '../components/LoadingSpinner'
import { Send } from 'lucide-react'

function formatTime(dateStr: string | undefined): string {
  if (!dateStr) return '--'
  try {
    return new Date(dateStr).toLocaleString('en-IN', {
      dateStyle: 'short',
      timeStyle: 'short',
    })
  } catch {
    return dateStr
  }
}

export default function Delivery() {
  const { data: deliveries, isLoading, error } = useDeliveryLog(100)

  if (isLoading) return <PageLoader label="Loading delivery log..." />

  if (error) {
    return (
      <div className="text-center py-12">
        <p className="text-red-600 text-sm">Failed to load delivery log</p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Delivery Log</h1>
        <p className="text-sm text-slate-500 mt-1">
          {deliveries?.length ?? 0} delivery records
        </p>
      </div>

      {!deliveries || deliveries.length === 0 ? (
        <div className="card card-body text-center py-12">
          <Send size={24} className="text-slate-300 mx-auto mb-2" />
          <p className="text-slate-500 text-sm">No deliveries recorded yet</p>
        </div>
      ) : (
        <div className="table-container">
          <table>
            <thead>
              <tr>
                <th>Station</th>
                <th>Channel</th>
                <th>Recipient</th>
                <th>Status</th>
                <th>Message</th>
                <th>Delivered</th>
              </tr>
            </thead>
            <tbody>
              {deliveries.map((d, i) => (
                <tr key={d.id ?? i}>
                  <td className="font-medium text-slate-900">
                    {d.station_name || d.station_id || '--'}
                  </td>
                  <td>
                    {d.channel ? (
                      <span className="badge-blue">{d.channel}</span>
                    ) : (
                      '--'
                    )}
                  </td>
                  <td className="text-slate-600 text-xs max-w-[10rem] truncate">
                    {d.recipient || '--'}
                  </td>
                  <td>
                    <StatusBadge status={d.status} />
                  </td>
                  <td className="max-w-xs">
                    {d.message_preview ? (
                      <span className="text-sm text-slate-600 line-clamp-2">
                        {d.message_preview}
                      </span>
                    ) : (
                      '--'
                    )}
                  </td>
                  <td className="text-xs text-slate-500">
                    {formatTime(d.delivered_at || d.created_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
