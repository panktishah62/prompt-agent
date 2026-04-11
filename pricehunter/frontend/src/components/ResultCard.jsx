const medalClasses = {
  1: 'border-amber-300/40 bg-amber-300/10 text-amber-200',
  2: 'border-slate-300/40 bg-slate-200/10 text-slate-100',
  3: 'border-orange-400/40 bg-orange-400/10 text-orange-200',
}

function formatPrice(price) {
  if (price == null) {
    return 'Quote unavailable'
  }
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0,
  }).format(price)
}

function ResultCard({ result, rank }) {
  const badgeClass =
    result.source_type === 'offline'
      ? 'border-mint/40 bg-mint/10 text-mint'
      : 'border-sky-400/40 bg-sky-400/10 text-sky-200'

  return (
    <article
      className="result-card group relative overflow-hidden rounded-[2rem] border border-white/10 bg-[linear-gradient(180deg,rgba(255,255,255,0.08),rgba(255,255,255,0.04))] p-6 shadow-soft transition hover:-translate-y-1 hover:border-mint/30"
      style={{ animationDelay: `${rank * 90}ms` }}
    >
      <div className="absolute inset-x-0 top-0 h-px bg-[linear-gradient(90deg,transparent,rgba(0,255,136,0.8),transparent)] opacity-60" />
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <div
            className={`rounded-2xl border px-3 py-2 font-display text-lg font-black ${
              medalClasses[rank] || 'border-white/10 bg-white/5 text-white'
            }`}
          >
            #{rank}
          </div>
          <div className={`rounded-full border px-3 py-1 text-xs font-bold uppercase tracking-[0.25em] ${badgeClass}`}>
            {result.source_type}
          </div>
          {rank === 1 && (
            <div className="rounded-full border border-mint/40 bg-mint/[0.15] px-3 py-1 text-xs font-bold uppercase tracking-[0.25em] text-mint">
              Best Deal
            </div>
          )}
        </div>

        {result.negotiated && (
          <div className="rounded-full border border-emerald-300/30 bg-emerald-300/10 px-3 py-1 text-xs uppercase tracking-[0.25em] text-emerald-100">
            Negotiated
          </div>
        )}
      </div>

      <div className="mt-6">
        <p className="text-sm uppercase tracking-[0.24em] text-slate-400">Vendor / Platform</p>
        <h3 className="mt-2 font-display text-2xl font-black text-white">{result.name}</h3>
      </div>

      <div className="mt-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm uppercase tracking-[0.24em] text-slate-400">Price</p>
          <p className="mt-2 font-display text-4xl font-black text-white">{formatPrice(result.price)}</p>
        </div>
        <div className="text-right">
          <p className="text-sm uppercase tracking-[0.24em] text-slate-400">Delivery</p>
          <p className="mt-2 text-lg font-semibold text-slate-100">{result.delivery_time || 'Not specified'}</p>
        </div>
      </div>

      <div className="mt-6 grid gap-3 text-sm text-slate-300">
        <div className="flex items-center justify-between">
          <span>Availability</span>
          <span className={result.availability ? 'text-mint' : 'text-rose-300'}>
            {result.availability ? 'In stock' : 'Unavailable'}
          </span>
        </div>
        <div className="flex items-center justify-between">
          <span>Confidence</span>
          <span>{Math.round(result.confidence * 100)}%</span>
        </div>
        <div className="h-2 overflow-hidden rounded-full bg-white/10">
          <div
            className="h-full rounded-full bg-[linear-gradient(90deg,#00ff88,#00b8ff)]"
            style={{ width: `${Math.max(10, Math.round(result.confidence * 100))}%` }}
          />
        </div>
        {result.address && <p className="text-slate-400">{result.address}</p>}
        {result.notes && <p className="text-slate-400">{result.notes}</p>}
        {result.is_mock && <p className="text-xs uppercase tracking-[0.22em] text-amber-200/90">Demo data</p>}
      </div>
    </article>
  )
}

export default ResultCard
