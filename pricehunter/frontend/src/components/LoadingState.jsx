import { useEffect, useState } from 'react'

const stages = [
  'Understanding your query...',
  'Searching online platforms...',
  'Calling nearby vendors...',
  'Comparing results...',
]

function LoadingState() {
  const [index, setIndex] = useState(0)

  useEffect(() => {
    const intervalId = window.setInterval(() => {
      setIndex((current) => (current + 1) % stages.length)
    }, 1800)

    return () => window.clearInterval(intervalId)
  }, [])

  return (
    <section className="mt-10 rounded-[2rem] border border-white/10 bg-white/5 p-6 shadow-soft backdrop-blur">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-[0.3em] text-mint/80">Search in progress</p>
          <p className="mt-3 font-display text-3xl font-black text-white">{stages[index]}</p>
          <p className="mt-2 max-w-2xl text-sm text-slate-300">
            Voice verification can take a little longer. The engine keeps working across both pipelines in parallel.
          </p>
        </div>
        <div className="grid grid-cols-4 gap-2">
          {stages.map((stage, stageIndex) => (
            <div
              key={stage}
              className={`h-3 w-16 rounded-full transition ${
                stageIndex <= index ? 'bg-mint shadow-[0_0_20px_rgba(0,255,136,0.3)]' : 'bg-white/10'
              }`}
            />
          ))}
        </div>
      </div>

      <div className="mt-8 overflow-hidden rounded-full bg-white/10">
        <div
          className="loading-bar h-3 rounded-full bg-[linear-gradient(90deg,#00ff88,#00b8ff,#00ff88)]"
          style={{ width: `${((index + 1) / stages.length) * 100}%` }}
        />
      </div>
    </section>
  )
}

export default LoadingState
