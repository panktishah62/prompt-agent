import { useEffect, useState } from 'react'

function LocationPrompt({
  isOpen,
  isResolving,
  error,
  initialValue,
  onUseCurrentLocation,
  onConfirmManual,
}) {
  const [manualLocation, setManualLocation] = useState(initialValue)

  useEffect(() => {
    setManualLocation(initialValue)
  }, [initialValue])

  if (!isOpen) {
    return null
  }

  const handleSubmit = (event) => {
    event.preventDefault()
    if (!manualLocation.trim()) {
      return
    }
    onConfirmManual(manualLocation.trim())
  }

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-ink/75 px-4 backdrop-blur-md">
      <div className="w-full max-w-xl rounded-[2rem] border border-white/10 bg-[linear-gradient(180deg,rgba(17,25,43,0.96),rgba(10,15,28,0.94))] p-6 shadow-soft">
        <p className="text-xs uppercase tracking-[0.3em] text-mint/80">Set your search zone</p>
        <h2 className="mt-4 font-display text-3xl font-black text-white">Where should PriceHunter search?</h2>
        <p className="mt-3 text-sm text-slate-300">
          Share your current location for a Swiggy-style experience, or type your city or area manually.
        </p>

        <div className="mt-6 grid gap-3 sm:grid-cols-[1fr_auto]">
          <button
            type="button"
            onClick={onUseCurrentLocation}
            disabled={isResolving}
            className="rounded-[1.4rem] border border-mint/30 bg-mint/10 px-5 py-4 text-left transition hover:border-mint/60 hover:bg-mint/15 disabled:cursor-not-allowed disabled:opacity-60"
          >
            <p className="font-display text-lg font-bold text-white">
              {isResolving ? 'Detecting your location...' : 'Use my current location'}
            </p>
            <p className="mt-1 text-sm text-slate-300">We will convert browser location into a search area before we start.</p>
          </button>
        </div>

        <form onSubmit={handleSubmit} className="mt-5">
          <label className="block">
            <span className="mb-2 block text-xs uppercase tracking-[0.24em] text-slate-500">Manual location</span>
            <input
              value={manualLocation}
              onChange={(event) => setManualLocation(event.target.value)}
              placeholder="Rajkot, Ahmedabad, Kotecha Chowk..."
              className="w-full rounded-[1.4rem] border border-white/10 bg-ink-soft px-4 py-4 text-white outline-none transition focus:border-mint/60 focus:ring-2 focus:ring-mint/20"
            />
          </label>
          <button
            type="submit"
            className="mt-4 rounded-[1.4rem] bg-[linear-gradient(135deg,#00ff88,#00b8ff)] px-5 py-4 font-display text-sm font-black uppercase tracking-[0.22em] text-ink transition hover:scale-[1.01]"
          >
            Confirm location
          </button>
        </form>

        {error && (
          <div className="mt-4 rounded-2xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-100">
            {error}
          </div>
        )}
      </div>
    </div>
  )
}

export default LocationPrompt
