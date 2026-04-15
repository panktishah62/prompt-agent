function SummaryRow({ label, value, pending = false }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.04] px-4 py-3">
      <p className="text-[11px] uppercase tracking-[0.26em] text-slate-500">{label}</p>
      <p className={`mt-2 text-sm ${pending ? 'text-slate-400' : 'text-white'}`}>
        {value || 'Waiting for input'}
      </p>
    </div>
  )
}

function formatIntent(intent) {
  return intent ? intent.replace('_', ' ') : ''
}

function ConversationSummary({ state }) {
  if (!state) {
    return (
      <section className="rounded-[2rem] border border-white/10 bg-white/5 p-5 shadow-soft backdrop-blur">
        <p className="text-xs uppercase tracking-[0.3em] text-mint/80">Search Checklist</p>
        <p className="mt-3 text-sm text-slate-300">
          I&apos;ll collect the exact product or service, urgency, intent, and category before searching.
        </p>
      </section>
    )
  }

  return (
    <section className="rounded-[2rem] border border-white/10 bg-white/5 p-5 shadow-soft backdrop-blur">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-[0.3em] text-mint/80">Search Checklist</p>
          <h2 className="mt-3 font-display text-2xl font-black text-white">Session details</h2>
        </div>
        {state.search_strategy && (
          <div className="rounded-full border border-sky-400/30 bg-sky-400/10 px-3 py-1 text-xs uppercase tracking-[0.22em] text-sky-200">
            {state.search_strategy} search
          </div>
        )}
      </div>

      <div className="mt-5 grid gap-3 sm:grid-cols-2">
        <SummaryRow
          label="Exact product / service"
          value={state.product}
          pending={state.missing_fields?.includes('product')}
        />
        <SummaryRow
          label="Urgency"
          value={state.urgency}
          pending={state.missing_fields?.includes('urgency')}
        />
        <SummaryRow
          label="Intent"
          value={formatIntent(state.intent)}
          pending={state.missing_fields?.includes('intent')}
        />
        <SummaryRow
          label="Category"
          value={state.category}
          pending={state.missing_fields?.includes('category')}
        />
      </div>
    </section>
  )
}

export default ConversationSummary
