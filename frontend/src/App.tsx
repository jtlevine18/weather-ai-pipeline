import { Routes, Route, Navigate } from 'react-router-dom'
import { ProtectedRoute } from './auth/ProtectedRoute'
import { Layout } from './components/Layout'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Stations from './pages/Stations'
import StationDetail from './pages/StationDetail'
import Forecasts from './pages/Forecasts'
import Advisories from './pages/Advisories'
import Pipeline from './pages/Pipeline'
// Delivery is now a tab inside Advisories and System pages

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }
      >
        <Route path="/" element={<Dashboard />} />
        <Route path="/stations" element={<Stations />} />
        <Route path="/stations/:id" element={<StationDetail />} />
        <Route path="/forecasts" element={<Forecasts />} />
        <Route path="/advisories" element={<Advisories />} />
        <Route path="/pipeline" element={<Pipeline />} />
        {/* Delivery is now a tab in Advisories + System */}
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
