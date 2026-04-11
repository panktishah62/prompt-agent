function Header() {
  return (
    <header className="sticky top-0 z-20 border-b border-white/10 bg-ink/80 backdrop-blur-xl">
      <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-4 sm:px-6 lg:px-8">
        <div>
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-2xl border border-mint/30 bg-mint/10 text-mint shadow-[0_0_30px_rgba(0,255,136,0.15)]">
              <svg viewBox="0 0 24 24" className="h-5 w-5 fill-current" aria-hidden="true">
                <path d="M13.2 2 5 13h5l-1.2 9L19 10h-5.1L13.2 2Z" />
              </svg>
            </div>
            <div>
              <p className="font-display text-2xl font-black tracking-tight text-white">PriceHunter</p>
              <p className="text-xs uppercase tracking-[0.28em] text-slate-400">
                Online + Offline. Every price. One search.
              </p>
            </div>
          </div>
        </div>
        <div className="hidden rounded-full border border-white/10 bg-white/5 px-4 py-2 text-xs uppercase tracking-[0.25em] text-slate-300 md:block">
          Fast compare mode
        </div>
      </div>
    </header>
  )
}

export default Header
