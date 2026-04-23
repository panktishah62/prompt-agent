const statusTone = {
  pending: 'border-white/10 bg-white/5 text-slate-300',
  running: 'border-sky-400/30 bg-sky-400/10 text-sky-200',
  completed: 'border-mint/40 bg-mint/10 text-mint',
  failed: 'border-rose-400/40 bg-rose-400/10 text-rose-200',
}

function SearchProgressPanel({ progress }) {
  const completedSteps = progress.steps.filter((step) => step.status === 'completed').length
  const totalSteps = progress.steps.length
  const vendors = progress.discovered_vendors || []
  const platforms = progress.online_platforms || []

  return (
    <section className="space-y-6">
      <div className="rounded-[2rem] border border-white/10 bg-white/5 p-6 shadow-soft backdrop-blur">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-[0.3em] text-mint/80">Search progress</p>
            <h2 className="mt-3 font-display text-3xl font-black text-white">
              {progress.status === 'completed'
                ? 'Search complete'
                : progress.status === 'failed'
                  ? 'Search interrupted'
                  : 'Vendors found. Fetching live details.'}
            </h2>
            <p className="mt-2 text-sm text-slate-300">
              {vendors.length} offline vendors found near {progress.query.location}. {platforms.length} online platforms are being checked in parallel.
            </p>
          </div>
          <div className={`rounded-full border px-4 py-2 text-xs font-bold uppercase tracking-[0.24em] ${statusTone[progress.status]}`}>
            {progress.status}
          </div>
        </div>

        <div className="mt-5 overflow-hidden rounded-full bg-white/10">
          <div
            className="h-3 rounded-full bg-[linear-gradient(90deg,#00ff88,#00b8ff)] transition-all"
            style={{ width: `${totalSteps ? Math.max(10, Math.round((completedSteps / totalSteps) * 100)) : 10}%` }}
          />
        </div>

        <p className="mt-3 text-sm text-slate-400">
          {completedSteps} of {totalSteps} tasks completed
          {progress.partial_results?.length ? ` | ${progress.partial_results.length} priced result(s) captured so far` : ''}
        </p>
      </div>

      {vendors.length > 0 && (
        <div className="rounded-[2rem] border border-white/10 bg-white/5 p-6 shadow-soft backdrop-blur">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-xs uppercase tracking-[0.3em] text-mint/80">Nearby vendors</p>
              <h3 className="mt-2 font-display text-2xl font-black text-white">
                Found {vendors.length} callable offline vendors
              </h3>
            </div>
            <div className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs uppercase tracking-[0.22em] text-slate-300">
              Top 10
            </div>
          </div>

          <div className="mt-5 grid gap-3">
            {vendors.slice(0, 10).map((vendor) => (
              <div
                key={vendor.place_id || vendor.phone}
                className="flex flex-col gap-2 rounded-2xl border border-white/10 bg-white/[0.04] px-4 py-4 sm:flex-row sm:items-center sm:justify-between"
              >
                <div>
                  <p className="text-sm font-semibold text-white">{vendor.name}</p>
                  <p className="mt-1 text-sm text-slate-400">{vendor.address}</p>
                </div>
                <a href={`tel:${vendor.phone}`} className="text-sm text-sky-200 transition hover:text-mint">
                  {vendor.phone}
                </a>
              </div>
            ))}
          </div>
        </div>
      )}

      {platforms.length > 0 && (
        <div className="rounded-[2rem] border border-white/10 bg-white/5 p-6 shadow-soft backdrop-blur">
          <p className="text-xs uppercase tracking-[0.3em] text-mint/80">Online coverage</p>
          <div className="mt-4 flex flex-wrap gap-2">
            {platforms.map((platform) => (
              <div
                key={platform}
                className="rounded-full border border-sky-400/30 bg-sky-400/10 px-3 py-2 text-xs uppercase tracking-[0.22em] text-sky-200"
              >
                {platform}
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="rounded-[2rem] border border-white/10 bg-white/5 p-6 shadow-soft backdrop-blur">
        <p className="text-xs uppercase tracking-[0.3em] text-mint/80">Live task log</p>
        <div className="mt-5 space-y-3">
          {progress.steps.map((step) => (
            <div
              key={step.id}
              className="flex flex-col gap-2 rounded-2xl border border-white/10 bg-white/[0.04] px-4 py-4 sm:flex-row sm:items-center sm:justify-between"
            >
              <div>
                <p className="text-sm font-semibold text-white">{step.label}</p>
                <p className="mt-1 text-sm text-slate-400">{step.detail || 'Waiting for update.'}</p>
              </div>
              <div className={`rounded-full border px-3 py-1 text-xs uppercase tracking-[0.22em] ${statusTone[step.status]}`}>
                {step.status}
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

export default SearchProgressPanel
