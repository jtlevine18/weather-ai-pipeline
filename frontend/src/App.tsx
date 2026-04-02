import { useCallback, useEffect, useState } from 'react'
import { Routes, Route, Navigate, useNavigate, useSearchParams, useLocation } from 'react-router-dom'
import Joyride, { type CallBackProps, STATUS, EVENTS, ACTIONS } from 'react-joyride'
import { Layout } from './components/Layout'
import Dashboard from './pages/Dashboard'
import Stations from './pages/Stations'
import StationDetail from './pages/StationDetail'
import Forecasts from './pages/Forecasts'
import Advisories from './pages/Advisories'
import Pipeline from './pages/Pipeline'
import { tourSteps, tourStyles, stepRoutes } from './lib/tour'

export default function App() {
  const [searchParams] = useSearchParams()
  const location = useLocation()
  const [runTour, setRunTour] = useState(false)
  const [stepIndex, setStepIndex] = useState(0)
  const navigate = useNavigate()

  // Auto-start on first visit, or when ?tour=true
  useEffect(() => {
    const forced = searchParams.get('tour') === 'true'
    const seen = localStorage.getItem('weather_tour_v2') === '1'
    if (forced || !seen) {
      const timer = setTimeout(() => {
        if (location.pathname !== '/') navigate('/')
        setTimeout(() => {
          setStepIndex(0)
          setRunTour(true)
          localStorage.setItem('weather_tour_v2', '1')
        }, 300)
      }, 1500)
      return () => clearTimeout(timer)
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Listen for relaunch from the tour button
  useEffect(() => {
    function handleRelaunch() {
      navigate('/')
      setTimeout(() => {
        setStepIndex(0)
        setRunTour(true)
      }, 400)
    }
    window.addEventListener('relaunch-tour', handleRelaunch)
    return () => window.removeEventListener('relaunch-tour', handleRelaunch)
  }, [navigate])

  const handleJoyrideCallback = useCallback(
    (data: CallBackProps) => {
      const { status, action, index, type } = data

      if (status === STATUS.FINISHED || status === STATUS.SKIPPED || action === ACTIONS.CLOSE) {
        setRunTour(false)
        setStepIndex(0)
        return
      }

      if (type === EVENTS.STEP_AFTER) {
        const nextIndex = action === ACTIONS.PREV ? index - 1 : index + 1
        const nextRoute = stepRoutes[nextIndex]
        const currentRoute = stepRoutes[index]
        const needsNav = nextRoute !== undefined && nextRoute !== currentRoute

        // Always pause briefly so tooltip unmounts cleanly (prevents arrow ghost)
        setRunTour(false)

        if (needsNav) {
          navigate(nextRoute!)
          setTimeout(() => {
            setStepIndex(nextIndex)
            setRunTour(true)
          }, 800)
        } else {
          setTimeout(() => {
            setStepIndex(nextIndex)
            setRunTour(true)
          }, 150)
        }
      }
    },
    [navigate],
  )

  return (
    <>
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

      <Joyride
        steps={tourSteps}
        run={runTour}
        stepIndex={stepIndex}
        continuous
        showSkipButton
        showProgress
        scrollToFirstStep
        disableOverlayClose
        spotlightClicks={false}
        callback={handleJoyrideCallback}
        styles={tourStyles}
        floaterProps={{
          disableAnimation: false,
        }}
        locale={{
          back: 'Back',
          close: 'Close',
          last: 'Finish',
          next: 'Next',
          skip: 'Skip tour',
        }}
      />
    </>
  )
}
