import { useEffect, useMemo, useReducer, useRef, useState } from 'react'
import Header from './components/Header'
import LoadingState from './components/LoadingState'
import ResultsList from './components/ResultsList'
import ChatBubble from './components/ChatBubble'
import ConversationSummary from './components/ConversationSummary'
import LocationPrompt from './components/LocationPrompt'

const LOCATION_STORAGE_KEY = 'pricehunter-location'

const initialMessages = [
  {
    role: 'assistant',
    content:
      'Tell me what you want to find. I will lock in the exact product, urgency, intent, category, and location before I search.',
  },
]

const initialState = {
  isLoading: false,
  sessionId: '',
  messages: initialMessages,
  suggestedReplies: ['iPhone 16 128GB in Rajkot', 'boat earphones', 'paracetamol tablets'],
  data: null,
  error: '',
  conversationState: null,
}

function reducer(state, action) {
  switch (action.type) {
    case 'SEND_START':
      return {
        ...state,
        isLoading: true,
        error: '',
        messages: [...state.messages, { role: 'user', content: action.payload }],
      }
    case 'SEND_SUCCESS':
      return {
        ...state,
        isLoading: false,
        sessionId: action.payload.sessionId,
        suggestedReplies: action.payload.suggestedReplies,
        conversationState: action.payload.conversationState,
        data: action.payload.results ?? state.data,
        messages: [
          ...state.messages,
          { role: 'assistant', content: action.payload.assistantMessage },
        ],
      }
    case 'SEND_ERROR':
      return {
        ...state,
        isLoading: false,
        error: action.payload,
      }
    case 'RESET_SESSION':
      return {
        ...initialState,
        messages: [...initialMessages],
      }
    default:
      return state
  }
}

function App() {
  const [state, dispatch] = useReducer(reducer, initialState)
  const [input, setInput] = useState('')
  const [location, setLocation] = useState('')
  const [isLocationPromptOpen, setIsLocationPromptOpen] = useState(true)
  const [locationError, setLocationError] = useState('')
  const [isResolvingLocation, setIsResolvingLocation] = useState(false)
  const [locationAnnouncementShown, setLocationAnnouncementShown] = useState(false)
  const messagesEndRef = useRef(null)

  useEffect(() => {
    const savedLocation = window.localStorage.getItem(LOCATION_STORAGE_KEY)
    if (savedLocation) {
      setLocation(savedLocation)
      setIsLocationPromptOpen(false)
    }
  }, [])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [state.messages, state.isLoading])

  const headline = useMemo(() => {
    const product = state.conversationState?.product || state.data?.query?.product
    return product ? `Find the best path for ${product}` : 'Chat once. Search smarter.'
  }, [state.conversationState?.product, state.data?.query?.product])

  const apiBaseUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000'

  const rememberLocation = (value) => {
    setLocation(value)
    setIsLocationPromptOpen(false)
    setLocationError('')
    window.localStorage.setItem(LOCATION_STORAGE_KEY, value)
  }

  const handleConfirmManualLocation = (value) => {
    rememberLocation(value)
  }

  const handleUseCurrentLocation = async () => {
    if (!navigator.geolocation) {
      setLocationError('This browser does not support location access. Enter your city or area manually.')
      return
    }

    setIsResolvingLocation(true)
    setLocationError('')

    navigator.geolocation.getCurrentPosition(
      async (position) => {
        try {
          const response = await fetch(`${apiBaseUrl}/api/location/resolve`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              latitude: position.coords.latitude,
              longitude: position.coords.longitude,
            }),
          })

          if (!response.ok) {
            throw new Error('Could not resolve your current location.')
          }

          const payload = await response.json()
          rememberLocation(payload.location)
        } catch (error) {
          setLocationError('I could not convert your current position into a search area. Try entering it manually.')
        } finally {
          setIsResolvingLocation(false)
        }
      },
      () => {
        setIsResolvingLocation(false)
        setLocationError('Location permission was blocked. Enter your city or area manually.')
      },
      { enableHighAccuracy: true, timeout: 12000, maximumAge: 60000 },
    )
  }

  const handleSend = async (message) => {
    const trimmed = message.trim()
    if (!trimmed || state.isLoading) {
      return
    }
    if (!location) {
      setIsLocationPromptOpen(true)
      setLocationError('Please confirm your location before searching.')
      return
    }

    dispatch({ type: 'SEND_START', payload: trimmed })
    setInput('')

    const controller = new AbortController()
    const timeoutId = window.setTimeout(() => controller.abort(), 120000)

    try {
      const response = await fetch(`${apiBaseUrl}/api/chat/message`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: trimmed,
          session_id: state.sessionId || undefined,
          location,
        }),
        signal: controller.signal,
      })

      if (!response.ok) {
        throw new Error(`Chat failed with status ${response.status}`)
      }

      const payload = await response.json()
      dispatch({
        type: 'SEND_SUCCESS',
        payload: {
          sessionId: payload.session_id,
          assistantMessage: payload.assistant_message,
          suggestedReplies: payload.suggested_replies || [],
          conversationState: payload.state,
          results: payload.results || null,
        },
      })
      setLocationAnnouncementShown(true)
    } catch (error) {
      dispatch({
        type: 'SEND_ERROR',
        payload:
          error.name === 'AbortError'
            ? 'This step took longer than 120 seconds. Please try again or narrow the request.'
            : 'I hit a problem while continuing the conversation. Please try that message again.',
      })
    } finally {
      window.clearTimeout(timeoutId)
    }
  }

  const handleSubmit = (event) => {
    event.preventDefault()
    handleSend(input)
  }

  return (
    <div className="relative min-h-screen overflow-hidden bg-ink text-white">
      <LocationPrompt
        isOpen={isLocationPromptOpen}
        isResolving={isResolvingLocation}
        error={locationError}
        initialValue={location}
        onUseCurrentLocation={handleUseCurrentLocation}
        onConfirmManual={handleConfirmManualLocation}
      />

      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top,rgba(0,255,136,0.2),transparent_32%),radial-gradient(circle_at_bottom_right,rgba(33,110,255,0.18),transparent_30%)]" />
      <div className="pointer-events-none absolute inset-x-0 top-0 h-72 bg-[linear-gradient(180deg,rgba(255,255,255,0.05),transparent)]" />

      <Header />

      <main className="relative mx-auto w-full max-w-7xl px-4 pb-16 pt-10 sm:px-6 lg:px-8">
        <section className="mx-auto max-w-6xl text-center">
          <p className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-4 py-2 text-xs uppercase tracking-[0.35em] text-mint/80 shadow-soft">
            Conversational Search Intake
          </p>
          <h1 className="mt-6 font-display text-5xl font-black tracking-tight text-white sm:text-6xl">
            {headline}
          </h1>
          <p className="mx-auto mt-4 max-w-3xl text-base text-slate-300 sm:text-lg">
            I&apos;ll ask just enough to make the search precise, then decide whether to search online, offline, or both.
          </p>
        </section>

        <section className="mx-auto mt-6 max-w-6xl rounded-[1.6rem] border border-sky-400/20 bg-sky-400/10 px-4 py-4 shadow-soft backdrop-blur">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="text-xs uppercase tracking-[0.28em] text-sky-200">Search location</p>
              <p className="mt-1 text-base text-white">
                {location
                  ? `I’ll use ${location} for this search, similar to a Swiggy-style location lock.`
                  : 'Set your location before searching so I can search the right area.'}
              </p>
            </div>
            <button
              type="button"
              onClick={() => setIsLocationPromptOpen(true)}
              className="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-xs uppercase tracking-[0.24em] text-slate-200 transition hover:border-mint/30 hover:text-white"
            >
              {location ? 'Change location' : 'Set location'}
            </button>
          </div>
        </section>

        <section className="mt-10 grid gap-6 xl:grid-cols-[0.92fr_1.08fr]">
          <div className="rounded-[2rem] border border-white/10 bg-white/5 p-5 shadow-soft backdrop-blur">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 pb-4">
              <div>
                <p className="text-xs uppercase tracking-[0.3em] text-mint/80">Assistant</p>
                <h2 className="mt-2 font-display text-2xl font-black text-white">PriceHunter Chat</h2>
              </div>
              <div className="flex items-center gap-2">
                <div className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs uppercase tracking-[0.24em] text-slate-300">
                  Guided intake
                </div>
                <button
                  type="button"
                  onClick={() => dispatch({ type: 'RESET_SESSION' })}
                  className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs uppercase tracking-[0.24em] text-slate-300 transition hover:border-mint/30 hover:text-white"
                >
                  New search
                </button>
              </div>
            </div>

            <div className="mt-5 h-[28rem] space-y-4 overflow-y-auto pr-1">
              {location && !locationAnnouncementShown && (
                <ChatBubble
                  role="assistant"
                  content={`I found your search location as ${location}. I’ll use that for the next search unless you change it.`}
                />
              )}
              {state.messages.map((message, index) => (
                <ChatBubble key={`${message.role}-${index}`} role={message.role} content={message.content} />
              ))}
              {state.isLoading && (
                <ChatBubble
                  role="assistant"
                  content={`Working through that now. I’m confirming the search around ${location || 'your area'} before I continue.`}
                />
              )}
              <div ref={messagesEndRef} />
            </div>

            {state.suggestedReplies.length > 0 && (
              <div className="mt-5 flex flex-wrap gap-2">
                {state.suggestedReplies.map((reply) => (
                  <button
                    key={reply}
                    type="button"
                    onClick={() => handleSend(reply)}
                    disabled={state.isLoading}
                    className="rounded-full border border-white/10 bg-white/5 px-3 py-2 text-sm text-slate-200 transition hover:border-mint/30 hover:bg-mint/10 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {reply}
                  </button>
                ))}
              </div>
            )}

            <form onSubmit={handleSubmit} className="mt-5 flex gap-3">
              <input
                value={input}
                onChange={(event) => setInput(event.target.value)}
                placeholder={location ? `Search in ${location}...` : 'Reply here...'}
                className="w-full rounded-[1.4rem] border border-white/10 bg-ink-soft px-4 py-4 text-sm text-white outline-none transition focus:border-mint/60 focus:ring-2 focus:ring-mint/20"
              />
              <button
                type="submit"
                disabled={state.isLoading || !input.trim()}
                className="rounded-[1.4rem] bg-[linear-gradient(135deg,#00ff88,#00b8ff)] px-5 py-4 font-display text-sm font-black uppercase tracking-[0.22em] text-ink transition hover:scale-[1.01] disabled:cursor-not-allowed disabled:opacity-60"
              >
                Send
              </button>
            </form>

            {state.error && (
              <div className="mt-4 rounded-2xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-100">
                {state.error}
              </div>
            )}
          </div>

          <div className="space-y-6">
            <ConversationSummary state={state.conversationState} />

            {state.isLoading && <LoadingState />}

            {!state.isLoading && state.data && <ResultsList data={state.data} />}

            {!state.isLoading && !state.data && (
              <section className="rounded-[2rem] border border-white/10 bg-white/5 p-6 shadow-soft backdrop-blur">
                <p className="text-xs uppercase tracking-[0.3em] text-mint/80">What happens next</p>
                <div className="mt-4 grid gap-3 md:grid-cols-3">
                  {[
                    'I confirm the exact product so the search is specific enough to trust.',
                    'I lock the location first, then search around that area consistently.',
                    'Then I run online, offline, or both and rank the results together.',
                  ].map((item) => (
                    <div key={item} className="rounded-2xl border border-white/10 bg-white/[0.04] p-4 text-sm text-slate-200">
                      {item}
                    </div>
                  ))}
                </div>
              </section>
            )}
          </div>
        </section>
      </main>
    </div>
  )
}

export default App
