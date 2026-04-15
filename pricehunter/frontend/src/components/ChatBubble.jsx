function ChatBubble({ role, content }) {
  const isAssistant = role === 'assistant'

  return (
    <div className={`flex ${isAssistant ? 'justify-start' : 'justify-end'}`}>
      <div
        className={`max-w-[85%] rounded-[1.5rem] px-4 py-3 text-sm leading-6 shadow-soft ${
          isAssistant
            ? 'border border-white/10 bg-white/[0.06] text-slate-100'
            : 'bg-[linear-gradient(135deg,rgba(0,255,136,0.18),rgba(0,184,255,0.16))] text-white'
        }`}
      >
        <p className="mb-1 text-[11px] uppercase tracking-[0.28em] text-slate-400">
          {isAssistant ? 'PriceHunter' : 'You'}
        </p>
        <p>{content}</p>
      </div>
    </div>
  )
}

export default ChatBubble
