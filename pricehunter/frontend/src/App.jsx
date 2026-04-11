import { useMemo, useReducer } from 'react'
import Header from './components/Header'
import SearchBar from './components/SearchBar'
import LoadingState from './components/LoadingState'
import ResultsList from './components/ResultsList'

const initialState = {
  status: 'idle',
  data: null,
  error: '',
}

function reducer(state, action) {
  switch (action.type) {
    case 'SEARCH_START':
      return { status: 'loading', data: null, error: '' }
    case 'SEARCH_SUCCESS':
      return { status: 'results', data: action.payload, error: '' }
    case 'SEARCH_ERROR':
      return { status: 'error', data: null, error: action.payload }
    default:
      return state
  }
}

function App() {
  const [state, dispatch] = useReducer(reducer, initialState)

  const headline = useMemo(() => {
    if (state.status === 'results' && state.data?.query?.product) {
      return `Best live price paths for ${state.data.query.product}`
    }
    return 'Search once. Compare everywhere.'
  }, [state.data, state.status])

  const handleSearch = async ({ query, location }) => {
    dispatch({ type: 'SEARCH_START' })

    const controller = new AbortController()
    const timeoutId = window.setTimeout(() => controller.abort(), 120000)

    try {
      const response = await fetch(
        `${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/api/search`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ query, location }),
          signal: controller.signal,
        },
      )

      if (!response.ok) {
        throw new Error(`Search failed with status ${response.status}`)
      }

      const payload = await response.json()
      dispatch({ type: 'SEARCH_SUCCESS', payload })
    } catch (error) {
      const message =
        error.name === 'AbortError'
          ? 'The search took longer than 120 seconds. Try mock mode or a narrower query.'
          : 'Something went wrong while searching. Please try again in a moment.'
      dispatch({ type: 'SEARCH_ERROR', payload: message })
    } finally {
      window.clearTimeout(timeoutId)
    }
  }

  return (
    <div className="relative min-h-screen overflow-hidden bg-ink text-white">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top,rgba(0,255,136,0.2),transparent_32%),radial-gradient(circle_at_bottom_right,rgba(33,110,255,0.18),transparent_30%)]" />
      <div className="pointer-events-none absolute inset-x-0 top-0 h-72 bg-[linear-gradient(180deg,rgba(255,255,255,0.05),transparent)]" />

      <Header />

      <main className="relative mx-auto flex min-h-[calc(100vh-5rem)] w-full max-w-7xl flex-col px-4 pb-16 pt-10 sm:px-6 lg:px-8">
        <section className="mx-auto w-full max-w-5xl">
          <div className="mb-8 text-center">
            <p className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-4 py-2 text-xs uppercase tracking-[0.35em] text-mint/80 shadow-soft">
              Hybrid Price Engine
            </p>
            <h1 className="mt-6 font-display text-5xl font-black tracking-tight text-white sm:text-6xl">
              {headline}
            </h1>
            <p className="mx-auto mt-4 max-w-3xl text-base text-slate-300 sm:text-lg">
              Online marketplaces and local vendors, ranked together by price, speed, and confidence.
            </p>
          </div>

          <SearchBar onSearch={handleSearch} isLoading={state.status === 'loading'} />

          {state.status === 'idle' && (
            <section className="mt-10 grid gap-4 md:grid-cols-3">
              {[
                'Online marketplaces in parallel',
                'Nearby vendors discovered and called',
                'One ranked result set tuned to your intent',
              ].map((item) => (
                <div
                  key={item}
                  className="rounded-3xl border border-white/10 bg-white/5 p-5 text-left shadow-soft backdrop-blur"
                >
                  <p className="text-xs uppercase tracking-[0.3em] text-slate-400">PriceHunter Signal</p>
                  <p className="mt-3 text-lg font-semibold text-white">{item}</p>
                </div>
              ))}
            </section>
          )}

          {state.status === 'loading' && <LoadingState />}

          {state.status === 'error' && (
            <div className="mt-10 rounded-3xl border border-rose-500/30 bg-rose-500/10 p-6 text-rose-100 shadow-soft">
              <p className="font-display text-2xl font-bold">Search interrupted</p>
              <p className="mt-2 text-sm text-rose-100/90">{state.error}</p>
            </div>
          )}

          {state.status === 'results' && <ResultsList data={state.data} />}
        </section>
      </main>
    </div>
  )
}

export default App
