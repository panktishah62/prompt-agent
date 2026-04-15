import { useMemo, useState } from 'react'
import ResultCard from './ResultCard'

function deliveryToMinutes(value) {
  if (!value) {
    return Number.MAX_SAFE_INTEGER / 2
  }

  const normalized = value.toLowerCase()
  if (normalized.includes('pickup')) {
    return 0
  }
  if (normalized.includes('same day')) {
    return 360
  }
  if (normalized.includes('next morning')) {
    return 720
  }

  const match = normalized.match(/(\d+)(?:\s*-\s*(\d+))?\s*(mins?|minutes|hours?|days?)/)
  if (!match) {
    return Number.MAX_SAFE_INTEGER / 2
  }

  const first = Number(match[1])
  const second = match[2] ? Number(match[2]) : first
  const average = (first + second) / 2
  const unit = match[3]

  if (unit.startsWith('day')) {
    return average * 1440
  }
  if (unit.startsWith('hour')) {
    return average * 60
  }
  return average
}

function sortResults(results, sortBy) {
  const cloned = [...results]
  switch (sortBy) {
    case 'price':
      return cloned.sort((a, b) => (a.price ?? Number.MAX_SAFE_INTEGER) - (b.price ?? Number.MAX_SAFE_INTEGER))
    case 'delivery':
      return cloned.sort((a, b) => deliveryToMinutes(a.delivery_time) - deliveryToMinutes(b.delivery_time))
    default:
      return cloned
  }
}

function ResultsList({ data }) {
  const [sortBy, setSortBy] = useState('rank')
  const [sourceFilter, setSourceFilter] = useState('all')

  const filteredResults = useMemo(() => {
    const bySource =
      sourceFilter === 'all' ? data.results : data.results.filter((item) => item.source_type === sourceFilter)
    return sortResults(bySource, sortBy)
  }, [data.results, sortBy, sourceFilter])

  return (
    <section className="mt-10 space-y-6">
      <div className="rounded-[2rem] border border-white/10 bg-white/5 p-5 shadow-soft backdrop-blur">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.3em] text-mint/80">Result Summary</p>
            <h2 className="mt-3 font-display text-3xl font-black text-white">
              Found {data.results.length} results in {data.total_time_seconds} seconds
            </h2>
            <p className="mt-2 text-sm text-slate-300">
              {data.online_count} online, {data.offline_count} offline. Ranked for{' '}
              <span className="text-white">{data.query.intent.replace('_', ' ')}</span>.
            </p>
            <p className="mt-2 text-sm text-slate-400">
              Urgency: <span className="text-slate-200">{data.query.urgency}</span> | Strategy:{' '}
              <span className="text-slate-200">{data.search_strategy}</span>
            </p>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <label className="block text-sm text-slate-300">
              <span className="mb-2 block uppercase tracking-[0.25em] text-slate-500">Sort by</span>
              <select
                value={sortBy}
                onChange={(event) => setSortBy(event.target.value)}
                className="w-full rounded-2xl border border-white/10 bg-ink-soft px-4 py-3 text-white outline-none focus:border-mint/60"
              >
                <option value="rank">Best ranked</option>
                <option value="price">Lowest price</option>
                <option value="delivery">Delivery time</option>
              </select>
            </label>

            <label className="block text-sm text-slate-300">
              <span className="mb-2 block uppercase tracking-[0.25em] text-slate-500">Source</span>
              <select
                value={sourceFilter}
                onChange={(event) => setSourceFilter(event.target.value)}
                className="w-full rounded-2xl border border-white/10 bg-ink-soft px-4 py-3 text-white outline-none focus:border-sky-400/60"
              >
                <option value="all">All sources</option>
                <option value="online">Online only</option>
                <option value="offline">Offline only</option>
              </select>
            </label>
          </div>
        </div>
      </div>

      <div className="grid gap-5 xl:grid-cols-2">
        {filteredResults.map((result, index) => (
          <ResultCard
            key={result.id}
            result={result}
            rank={sortBy === 'rank' && sourceFilter === 'all' ? index + 1 : data.results.findIndex((item) => item.id === result.id) + 1}
          />
        ))}
      </div>
    </section>
  )
}

export default ResultsList
