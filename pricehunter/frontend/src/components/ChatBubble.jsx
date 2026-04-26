function formatPrice(value) {
  if (value === null || value === undefined) {
    return null
  }
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0,
  }).format(value)
}

function ChatBubble({ message }) {
  const isAssistant = message.role === 'assistant'
  const results = message.kind === 'results' ? message.payload?.results || [] : []

  return (
    <div className={`flex ${isAssistant ? 'justify-start' : 'justify-end'}`}>
      <div
        className={`max-w-[88%] rounded-[1.5rem] px-4 py-3 text-sm leading-6 ${
          isAssistant
            ? 'border border-slate-200 bg-white text-slate-800 shadow-[0_12px_32px_rgba(15,23,42,0.06)]'
            : 'bg-slate-900 text-white shadow-[0_14px_34px_rgba(15,23,42,0.16)]'
        }`}
      >
        <p className="mb-1 text-[11px] uppercase tracking-[0.28em] text-slate-400">
          {isAssistant ? 'PriceHunter' : 'You'}
        </p>
        <p className="whitespace-pre-wrap">{message.content}</p>

        {results.length > 0 ? (
          <div className="mt-4 space-y-3">
            {results.map((result) => (
              <div key={result.id} className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="text-sm font-semibold text-slate-900">{result.name}</p>
                    <p className="mt-1 text-xs uppercase tracking-[0.2em] text-slate-400">
                      {result.source_type === 'online' ? 'Online' : 'Offline'}
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="text-sm font-semibold text-slate-900">{formatPrice(result.price) || 'Price pending'}</p>
                    {result.delivery_time ? (
                      <p className="mt-1 text-xs text-slate-500">{result.delivery_time}</p>
                    ) : null}
                  </div>
                </div>
                {result.notes ? <p className="mt-3 text-sm text-slate-600">{result.notes}</p> : null}
              </div>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  )
}

export default ChatBubble
