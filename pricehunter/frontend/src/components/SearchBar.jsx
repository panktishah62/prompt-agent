import { useState } from 'react'

function SearchBar({ onSearch, isLoading }) {
  const [query, setQuery] = useState('')
  const [location, setLocation] = useState('')

  const handleSubmit = (event) => {
    event.preventDefault()
    if (!query.trim() || isLoading) {
      return
    }
    onSearch({ query: query.trim(), location: location.trim() })
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="rounded-[2rem] border border-white/10 bg-white/[0.06] p-4 shadow-soft backdrop-blur-xl sm:p-6"
    >
      <div className="grid gap-4 lg:grid-cols-[1fr_auto]">
        <label className="block">
          <span className="sr-only">Product query</span>
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="What are you looking for? e.g., cheapest iPhone 15 near Rajkot"
            className="w-full rounded-[1.6rem] border border-white/10 bg-ink-soft px-5 py-5 font-body text-base text-white outline-none transition focus:border-mint/60 focus:ring-2 focus:ring-mint/20"
          />
        </label>

        <button
          type="submit"
          disabled={isLoading}
          className="group rounded-[1.6rem] bg-[linear-gradient(135deg,#00ff88,#00b8ff)] px-7 py-4 font-display text-sm font-black uppercase tracking-[0.25em] text-ink transition hover:scale-[1.01] hover:shadow-[0_18px_45px_rgba(0,255,136,0.28)] disabled:cursor-not-allowed disabled:opacity-60"
        >
          <span className="inline-flex items-center gap-2">
            Search
            <span className="transition group-hover:translate-x-1">→</span>
          </span>
        </button>
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-[220px_1fr] sm:items-center">
        <label className="block">
          <span className="sr-only">Location</span>
          <input
            value={location}
            onChange={(event) => setLocation(event.target.value)}
            placeholder="Optional location override"
            className="w-full rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white outline-none transition focus:border-sky-400/70 focus:ring-2 focus:ring-sky-400/20"
          />
        </label>
        <p className="text-sm text-slate-400">
          Try queries like <span className="text-slate-200">"fastest delivery for tomatoes near me"</span> or{' '}
          <span className="text-slate-200">"best value laptop in Ahmedabad"</span>.
        </p>
      </div>
    </form>
  )
}

export default SearchBar
