import { Routes, Route, Navigate } from 'react-router-dom'
import { Layout } from './components/Layout'
import Dashboard from './pages/Dashboard'
import Stations from './pages/Stations'
import StationDetail from './pages/StationDetail'
import Forecasts from './pages/Forecasts'
import Advisories from './pages/Advisories'
import Pipeline from './pages/Pipeline'

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Dashboard />} />
        <Route path="/stations" element={<Stations />} />
        <Route path="/stations/:id" element={<StationDetail />} />
        <Route path="/forecasts" element={<Forecasts />} />
        <Route path="/advisories" element={<Advisories />} />
        <Route path="/pipeline" element={<Pipeline />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
