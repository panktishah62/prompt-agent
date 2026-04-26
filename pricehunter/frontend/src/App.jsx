import { useEffect, useMemo, useReducer, useRef, useState } from 'react'
import ChatBubble from './components/ChatBubble'
import LocationPrompt from './components/LocationPrompt'
import SessionSidebar from './components/SessionSidebar'

const LOCATION_STORAGE_KEY = 'pricehunter-location'
const DEVICE_ID_STORAGE_KEY = 'pricehunter-device-id'

function getOrCreateDeviceId() {
  const existing = window.localStorage.getItem(DEVICE_ID_STORAGE_KEY)
  if (existing) {
    return existing
  }
  const generated =
    window.crypto?.randomUUID?.() ||
    `device-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
  window.localStorage.setItem(DEVICE_ID_STORAGE_KEY, generated)
  return generated
}

function formatList(items, maxVisible = 6) {
  if (!items?.length) {
    return ''
  }
  if (items.length <= maxVisible) {
    return items.join(', ')
  }
  return `${items.slice(0, maxVisible).join(', ')}, and ${items.length - maxVisible} more`
}

function buildInitialSearchMessages(progress) {
  if (!progress) {
    return []
  }

  const product = progress.query?.product || 'your product'
  const location = progress.query?.location || 'your area'
  const vendorNames = (progress.discovered_vendors || []).map((vendor) => vendor.name)
  const messages = [
    {
      message_id: `search-start-${progress.search_id}`,
      role: 'assistant',
      kind: 'status',
      content: `I’ve started the search for ${product} in ${location}. I’m running the online and offline search in parallel now.`,
      created_at: new Date().toISOString(),
    },
  ]

  if (vendorNames.length > 0) {
    messages.push({
      message_id: `vendor-list-${progress.search_id}`,
      role: 'assistant',
      kind: 'status',
      content: `I found ${vendorNames.length} relevant offline vendor${vendorNames.length > 1 ? 's' : ''}: ${formatList(vendorNames)}. I’m contacting them now.`,
      created_at: new Date().toISOString(),
    })
  }

  if ((progress.online_platforms || []).length > 0) {
    messages.push({
      message_id: `online-start-${progress.search_id}`,
      role: 'assistant',
      kind: 'status',
      content:
        'I’m also checking online platforms for live prices and direct product links. I’ll share those here as soon as they appear.',
      created_at: new Date().toISOString(),
    })
  }

  return messages
}

function buildResultMessages(progress, newResults) {
  const online = newResults.filter((result) => result.source_type === 'online')
  const offline = newResults.filter((result) => result.source_type === 'offline')
  const messages = []

  if (online.length > 0) {
    messages.push({
      message_id: `partial-online-${progress.search_id}-${online.map((result) => result.id).join('-')}`,
      role: 'assistant',
      kind: 'results',
      content:
        online.length === 1
          ? `I found an online price on ${online[0].name}. Here’s the direct product link.`
          : `I found ${online.length} online price matches with direct product links.`,
      payload: { results: online },
      created_at: new Date().toISOString(),
    })
  }

  if (offline.length > 0) {
    messages.push({
      message_id: `partial-offline-${progress.search_id}-${offline.map((result) => result.id).join('-')}`,
      role: 'assistant',
      kind: 'results',
      content:
        offline.length === 1
          ? `I received a local vendor quote from ${offline[0].name}.`
          : `I received ${offline.length} more local vendor quote${offline.length > 1 ? 's' : ''}.`,
      payload: { results: offline },
      created_at: new Date().toISOString(),
    })
  }

  return messages
}

const initialMessages = [
  {
    message_id: 'welcome',
    role: 'assistant',
    kind: 'text',
    created_at: new Date().toISOString(),
    content:
      'Tell me what you want to find. I’ll handle the product details, search online and offline, and keep the full search conversation here.',
  },
]

const initialState = {
  isLoading: false,
  sessions: [],
  sessionsLoading: true,
  sessionId: '',
  messages: initialMessages,
  suggestedReplies: ['iPhone 16 128GB in Rajkot', 'boat earphones', 'paracetamol tablets'],
  searchProgress: null,
  activeSearchId: '',
  error: '',
  conversationState: null,
}

function reducer(state, action) {
  switch (action.type) {
    case 'SET_SESSIONS':
      return {
        ...state,
        sessions: action.payload,
        sessionsLoading: false,
      }
    case 'LOAD_SESSION':
      return {
        ...state,
        isLoading: false,
        error: '',
        sessionId: action.payload.sessionId,
        messages: action.payload.messages.length > 0 ? action.payload.messages : initialMessages,
        conversationState: action.payload.conversationState,
        suggestedReplies: [],
        searchProgress: null,
        activeSearchId: action.payload.activeSearchId || '',
      }
    case 'SEND_START':
      return {
        ...state,
        isLoading: true,
        error: '',
        searchProgress: state.searchProgress?.status === 'completed' ? null : state.searchProgress,
        messages: [
          ...state.messages,
          {
            message_id: `user-${Date.now()}`,
            role: 'user',
            kind: 'text',
            content: action.payload,
            created_at: new Date().toISOString(),
          },
        ],
      }
    case 'SEND_SUCCESS':
      return {
        ...state,
        isLoading: false,
        sessionId: action.payload.sessionId,
        suggestedReplies: action.payload.suggestedReplies,
        conversationState: action.payload.conversationState,
        searchProgress: action.payload.searchProgress ?? state.searchProgress,
        activeSearchId: action.payload.searchProgress?.search_id || state.activeSearchId,
        messages: [
          ...state.messages,
          {
            message_id: `assistant-${Date.now()}`,
            role: 'assistant',
            kind: 'text',
            content: action.payload.assistantMessage,
            created_at: new Date().toISOString(),
          },
        ],
      }
    case 'SEARCH_PROGRESS_UPDATE':
      return {
        ...state,
        searchProgress: action.payload,
        activeSearchId: action.payload.search_id || state.activeSearchId,
      }
    case 'APPEND_MESSAGE':
      if (state.messages.some((message) => message.message_id === action.payload.message_id)) {
        return state
      }
      return {
        ...state,
        messages: [...state.messages, action.payload],
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
        sessions: state.sessions,
        sessionsLoading: state.sessionsLoading,
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
  const [isLocationPromptOpen, setIsLocationPromptOpen] = useState(false)
  const [locationError, setLocationError] = useState('')
  const [isResolvingLocation, setIsResolvingLocation] = useState(false)
  const [locationAnnouncementShown, setLocationAnnouncementShown] = useState(false)
  const messagesEndRef = useRef(null)
  const progressTrackerRef = useRef({
    searchId: '',
    stepStates: {},
    resultIds: new Set(),
    finalMessageAdded: false,
  })

  useEffect(() => {
    const savedLocation = window.localStorage.getItem(LOCATION_STORAGE_KEY)
    if (savedLocation) {
      setLocation(savedLocation)
    }
  }, [])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [state.messages, state.isLoading])

  const headline = useMemo(() => {
    const product = state.conversationState?.product
    return product ? `Working on ${product}` : 'What can I help you find today?'
  }, [state.conversationState?.product])

  const apiBaseUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000'
  const deviceId = useMemo(() => getOrCreateDeviceId(), [])

  const fetchSessions = async () => {
    try {
      const response = await fetch(`${apiBaseUrl}/api/chat/sessions`, {
        headers: { 'X-Device-Id': deviceId },
      })
      if (!response.ok) {
        throw new Error('Failed to load chat sessions.')
      }
      const payload = await response.json()
      dispatch({ type: 'SET_SESSIONS', payload })
    } catch (error) {
      console.error(error)
      dispatch({ type: 'SET_SESSIONS', payload: [] })
    }
  }

  useEffect(() => {
    fetchSessions()
  }, [apiBaseUrl, deviceId])

  useEffect(() => {
    const searchId = state.activeSearchId
    const status = state.searchProgress?.status

    if (!searchId || status === 'completed' || status === 'failed') {
      return undefined
    }

    const intervalId = window.setInterval(async () => {
      try {
        const response = await fetch(`${apiBaseUrl}/api/chat/search/${searchId}`)
        if (!response.ok) {
          throw new Error(`Search status failed with status ${response.status}`)
        }
        const payload = await response.json()
        dispatch({ type: 'SEARCH_PROGRESS_UPDATE', payload })
      } catch (error) {
        console.error(error)
      }
    }, 2000)

    return () => window.clearInterval(intervalId)
  }, [apiBaseUrl, state.activeSearchId, state.searchProgress?.status])

  const persistSyntheticMessage = async (sessionId, message) => {
    if (!sessionId) {
      return
    }
    try {
      await fetch(`${apiBaseUrl}/api/chat/sessions/${sessionId}/messages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message_id: message.message_id,
          role: message.role,
          content: message.content,
          kind: message.kind,
          payload: message.payload || null,
        }),
      })
      fetchSessions()
    } catch (error) {
      console.error(error)
    }
  }

  const fetchSearchSnapshot = async (searchId) => {
    if (!searchId) {
      return
    }
    try {
      const response = await fetch(`${apiBaseUrl}/api/chat/search/${searchId}`)
      if (!response.ok) {
        throw new Error(`Search status failed with status ${response.status}`)
      }
      const payload = await response.json()
      dispatch({ type: 'SEARCH_PROGRESS_UPDATE', payload })
    } catch (error) {
      console.error(error)
    }
  }

  useEffect(() => {
    const progress = state.searchProgress
    if (!progress || !state.sessionId) {
      return
    }

    if (progressTrackerRef.current.searchId !== progress.search_id) {
      const initialMessages = buildInitialSearchMessages(progress)
      progressTrackerRef.current = {
        searchId: progress.search_id,
        stepStates: Object.fromEntries(progress.steps.map((step) => [step.id, step.status])),
        resultIds: new Set((progress.partial_results || []).map((result) => result.id)),
        finalMessageAdded: Boolean(progress.final_results),
      }
      initialMessages.forEach((message) => {
        dispatch({ type: 'APPEND_MESSAGE', payload: message })
        persistSyntheticMessage(state.sessionId, message)
      })
      return
    }

    const tracker = progressTrackerRef.current
    const nextMessages = []

    for (const step of progress.steps) {
      const previousStatus = tracker.stepStates[step.id]
      if (step.status !== previousStatus && step.status !== 'pending') {
        tracker.stepStates[step.id] = step.status
        nextMessages.push({
          message_id: `progress-${progress.search_id}-${step.id}-${step.status}`,
          role: 'assistant',
          kind: 'status',
          content:
            step.detail ||
            (step.status === 'failed' ? `${step.label} hit a problem.` : `${step.label} ${step.status}.`),
          created_at: new Date().toISOString(),
        })
      }
    }

    const newResults = (progress.partial_results || []).filter((result) => !tracker.resultIds.has(result.id))
    if (newResults.length > 0) {
      newResults.forEach((result) => tracker.resultIds.add(result.id))
      nextMessages.push(...buildResultMessages(progress, newResults))
    }

    if (progress.final_results && !tracker.finalMessageAdded) {
      tracker.finalMessageAdded = true
      nextMessages.push({
        message_id: `final-${progress.search_id}`,
        role: 'assistant',
        kind: 'results',
        content: 'The search is complete. Here’s the combined ranking across online and offline results.',
        payload: progress.final_results,
        created_at: new Date().toISOString(),
      })
    } else if (progress.status === 'failed' && !tracker.finalMessageAdded) {
      tracker.finalMessageAdded = true
      nextMessages.push({
        message_id: `failed-${progress.search_id}`,
        role: 'assistant',
        kind: 'status',
        content: progress.error || 'The search stopped before I could finish it.',
        created_at: new Date().toISOString(),
      })
    }

    nextMessages.forEach((message) => {
      dispatch({ type: 'APPEND_MESSAGE', payload: message })
      persistSyntheticMessage(state.sessionId, message)
    })
  }, [state.searchProgress, state.sessionId])

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

    dispatch({ type: 'SEND_START', payload: trimmed })
    setInput('')

    const controller = new AbortController()
    const timeoutId = window.setTimeout(() => controller.abort(), 120000)

    try {
      const response = await fetch(`${apiBaseUrl}/api/chat/message`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Device-Id': deviceId,
        },
        body: JSON.stringify({
          message: trimmed,
          session_id: state.sessionId || undefined,
          location: location || undefined,
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
          searchProgress: payload.search_progress || null,
        },
      })
      setLocationAnnouncementShown(true)
      fetchSessions()
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

  const handleOpenSession = async (sessionId) => {
    try {
      const response = await fetch(`${apiBaseUrl}/api/chat/sessions/${sessionId}`)
      if (!response.ok) {
        throw new Error('Failed to load chat session.')
      }
      const payload = await response.json()
      dispatch({
        type: 'LOAD_SESSION',
        payload: {
          sessionId: payload.session_id,
          messages: payload.messages,
          conversationState: payload.state,
          activeSearchId: payload.latest_search?.search_id || '',
        },
      })
      if (payload.latest_search?.search_id) {
        fetchSearchSnapshot(payload.latest_search.search_id)
      }
      if (payload.state?.location && payload.state.location !== 'unknown') {
        setLocation(payload.state.location)
      }
      setLocationAnnouncementShown(true)
    } catch (error) {
      console.error(error)
    }
  }

  return (
    <div className="min-h-screen bg-[#ecece6] text-slate-900">
      <LocationPrompt
        isOpen={isLocationPromptOpen}
        isResolving={isResolvingLocation}
        error={locationError}
        initialValue={location}
        onUseCurrentLocation={handleUseCurrentLocation}
        onConfirmManual={handleConfirmManualLocation}
      />

      <div className="grid min-h-screen lg:grid-cols-[320px_minmax(0,1fr)]">
        <div className="min-h-screen">
          <SessionSidebar
            sessions={state.sessions}
            activeSessionId={state.sessionId}
            onNewChat={() => {
              dispatch({ type: 'RESET_SESSION' })
              setLocationAnnouncementShown(false)
            }}
            onSelectSession={handleOpenSession}
            location={location}
            onChangeLocation={() => setIsLocationPromptOpen(true)}
          />
        </div>

        <main className="flex min-h-screen flex-col bg-[#fcfcf9]">
          <div className="border-b border-slate-200 px-6 py-5">
            <p className="text-xs font-semibold uppercase tracking-[0.28em] text-slate-400">Chat</p>
            <h2 className="mt-2 text-2xl font-semibold text-slate-900">{headline}</h2>
          </div>

          <div className="flex-1 overflow-y-auto px-6 py-8">
            <div className="mx-auto w-full max-w-4xl space-y-5">
              {location && !locationAnnouncementShown && state.messages.length === 1 ? (
                <ChatBubble
                  message={{
                    message_id: 'location-intro',
                    role: 'assistant',
                    kind: 'status',
                    content: `I’ll use ${location} for this conversation unless you change it.`,
                  }}
                />
              ) : null}

              {state.messages.map((message) => (
                <ChatBubble key={message.message_id} message={message} />
              ))}

              {state.isLoading ? (
                <ChatBubble
                  message={{
                    message_id: 'loading-message',
                    role: 'assistant',
                    kind: 'status',
                    content: 'Let me lock that in and line up the next step.',
                  }}
                />
              ) : null}

              <div ref={messagesEndRef} />
            </div>
          </div>

          <div className="border-t border-slate-200 bg-[#fcfcf9] px-6 py-5">
            <div className="mx-auto w-full max-w-4xl">
              {state.suggestedReplies.length > 0 ? (
                <div className="mb-4 flex flex-wrap gap-2">
                  {state.suggestedReplies.map((reply) => (
                    <button
                      key={reply}
                      type="button"
                      onClick={() => handleSend(reply)}
                      disabled={state.isLoading}
                      className="rounded-full border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 transition hover:border-slate-300 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {reply}
                    </button>
                  ))}
                </div>
              ) : null}

              <form onSubmit={handleSubmit} className="rounded-[1.75rem] border border-slate-200 bg-white p-3 shadow-[0_16px_40px_rgba(15,23,42,0.06)]">
                <div className="flex items-end gap-3">
                  <textarea
                    value={input}
                    onChange={(event) => setInput(event.target.value)}
                    rows={1}
                    placeholder={location ? `Ask anything in ${location}` : 'Ask anything'}
                    className="max-h-40 min-h-[48px] w-full resize-none border-0 bg-transparent px-3 py-2 text-base text-slate-900 outline-none placeholder:text-slate-400"
                  />
                  <button
                    type="submit"
                    disabled={state.isLoading || !input.trim()}
                    className="rounded-2xl bg-slate-900 px-5 py-3 text-sm font-medium text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    Send
                  </button>
                </div>
              </form>

              {state.error ? (
                <div className="mt-4 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
                  {state.error}
                </div>
              ) : null}
            </div>
          </div>
        </main>
      </div>
    </div>
  )
}

export default App
