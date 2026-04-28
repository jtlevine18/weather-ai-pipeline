import { useState, useRef, useEffect } from 'react'
import { X, Send, Search, Trash2 } from 'lucide-react'
import { apiFetch, ApiError } from '../api/client'
import { useFarmers } from '../api/hooks'
import type { FarmerSummary, FarmerDetail } from '../api/hooks'

interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

interface ChatResponse {
  response?: string
}

interface FarmerInfo {
  name: string
  district: string
  state: string
  crops: string[]
  area: number
}

const INITIAL_MSG: ChatMessage = {
  role: 'assistant',
  content:
    "Hi — I can explain how this system works, show forecasts for any station, or walk through a farmer's profile. " +
    "Try: 'How are forecasts generated?', 'Show the latest data for Chennai', or 'What does a farmer advisory look like?'",
}

function renderMarkdown(text: string): string {
  // Escape HTML first to prevent injection
  let html = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')

  // Bold: **text**
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')

  // Inline code: `text`
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>')

  // Process lines for lists and line breaks
  const lines = html.split('\n')
  const result: string[] = []
  let inList = false

  for (const line of lines) {
    const listMatch = line.match(/^- (.+)/)
    if (listMatch) {
      if (!inList) {
        result.push('<ul>')
        inList = true
      }
      result.push(`<li>${listMatch[1]}</li>`)
    } else {
      if (inList) {
        result.push('</ul>')
        inList = false
      }
      result.push(line)
    }
  }
  if (inList) {
    result.push('</ul>')
  }

  // Join with <br /> for non-list lines
  html = result.join('<br />')
  // Clean up extra <br /> around <ul> and </ul>
  html = html.replace(/<br \/><ul>/g, '<ul>')
  html = html.replace(/<\/ul><br \/>/g, '</ul>')
  html = html.replace(/<\/li><br \/><li>/g, '</li><li>')

  return html
}

export function ChatWidget() {
  const [open, setOpen] = useState(false)
  const [messages, setMessages] = useState<ChatMessage[]>(() => {
    try {
      const saved = sessionStorage.getItem('weather_chat_messages')
      if (saved) return JSON.parse(saved) as ChatMessage[]
    } catch {
      // ignore
    }
    return [INITIAL_MSG]
  })
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [farmerPhone, setFarmerPhone] = useState('')
  const [farmerInfo, setFarmerInfo] = useState<FarmerInfo | null>(null)
  const [lookingUp, setLookingUp] = useState(false)
  const [showDemoFarmers, setShowDemoFarmers] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const farmers = useFarmers({ enabled: open })

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    try { sessionStorage.setItem('weather_chat_messages', JSON.stringify(messages)) } catch {
      // ignore
    }
  }, [messages])

  async function lookupFarmer(phone: string) {
    if (!phone.trim()) return
    setLookingUp(true)
    try {
      const detail = await apiFetch<FarmerDetail>(`/api/farmers/${encodeURIComponent(phone.trim())}`)
      const info: FarmerInfo = {
        name: detail.aadhaar?.name || 'Unknown',
        district: detail.aadhaar?.district || '',
        state: detail.aadhaar?.state || '',
        crops: detail.primary_crops || [],
        area: detail.total_area || 0,
      }
      setFarmerInfo(info)
      setFarmerPhone(phone.trim())
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: `Identified: **${info.name}**\n- District: ${info.district}, ${info.state}\n- Crops: ${info.crops.join(', ')}\n- Area: ${info.area.toFixed(2)} ha`,
      }])
    } catch (err) {
      if (import.meta.env.DEV) {
        // eslint-disable-next-line no-console
        console.warn('lookupFarmer failed:', err)
      }
      const content =
        err instanceof ApiError && err.status >= 400 && err.status < 500
          ? 'No farmer found with that phone number.'
          : "Couldn't reach the server. Please try again."
      setMessages(prev => [...prev, { role: 'assistant', content }])
    } finally {
      setLookingUp(false)
    }
  }

  async function sendMessage() {
    if (!input.trim() || sending) return
    const userMsg = input.trim()
    setInput('')
    setMessages(prev => [...prev, { role: 'user', content: userMsg }])
    setSending(true)

    try {
      const resp = await apiFetch<ChatResponse>('/api/chat', {
        method: 'POST',
        body: JSON.stringify({
          message: userMsg,
          history: messages.slice(-10),
          farmer_phone: farmerPhone || undefined,
        }),
      })
      setMessages(prev => [...prev, { role: 'assistant', content: resp.response || 'No response.' }])
    } catch (err) {
      if (import.meta.env.DEV) {
        // eslint-disable-next-line no-console
        console.warn('sendMessage failed:', err)
      }
      const content =
        err instanceof ApiError && err.status >= 400 && err.status < 500
          ? 'That request was rejected by the server.'
          : "Couldn't reach the server. Please try again."
      setMessages(prev => [...prev, { role: 'assistant', content }])
    } finally {
      setSending(false)
    }
  }

  function clearChat() {
    setMessages([INITIAL_MSG])
    setFarmerPhone('')
    setFarmerInfo(null)
  }

  function selectDemoFarmer(f: FarmerSummary) {
    setFarmerPhone(f.phone)
    setShowDemoFarmers(false)
    lookupFarmer(f.phone)
  }

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        aria-label="Open farmer advisor chat"
        title="Ask the model"
        className="hidden lg:block fixed z-[1000]"
        style={{
          bottom: '72px',
          left: 0,
          width: '240px',
          textAlign: 'center',
          background: 'none',
          border: 'none',
          padding: '10px 14px',
          fontFamily: '"Space Grotesk", system-ui, sans-serif',
          fontSize: '13px',
          fontWeight: 500,
          color: '#fcfaf7',
          cursor: 'pointer',
          textUnderlineOffset: '4px',
        }}
      >
        → Ask the model
      </button>
    )
  }

  return (
    <div
      className="chat-widget-container fixed inset-0 lg:inset-auto lg:bottom-6 lg:right-6 z-[1000] flex flex-col overflow-hidden lg:w-[420px] lg:h-[540px] lg:max-w-[calc(100vw-48px)] lg:max-h-[calc(100vh-48px)]"
      style={{
        background: '#ffffff',
        border: '1px solid #e8e5e1',
        borderRadius: '4px',
      }}
    >
      <style>{`
        .chat-widget-container code {
          background: #fcfaf7;
          padding: 1px 4px;
          border-radius: 3px;
          font-size: 0.8rem;
          font-family: monospace;
        }
        .chat-widget-container ul {
          margin: 4px 0;
          padding-left: 16px;
        }
      `}</style>
      {/* Header */}
      <div
        className="flex items-center justify-between shrink-0"
        style={{
          padding: '16px 20px 12px 20px',
          borderBottom: '1px solid #e8e5e1',
          background: '#ffffff',
        }}
      >
        <div>
          <div className="eyebrow">Ask the model</div>
          <div
            style={{
              fontFamily: '"Source Serif 4", Georgia, serif',
              fontSize: '18px',
              color: '#1b1e2d',
              marginTop: '4px',
            }}
          >
            Farmer advisor
          </div>
        </div>
        <button
          onClick={() => setOpen(false)}
          aria-label="Close chat"
          style={{
            background: 'none',
            border: 'none',
            color: '#8d909e',
            cursor: 'pointer',
            padding: '4px',
          }}
        >
          <X size={18} />
        </button>
      </div>

      {/* Farmer Identity */}
      <div
        className="shrink-0"
        style={{
          padding: '14px 20px',
          borderBottom: '1px solid #e8e5e1',
          background: '#fcfaf7',
        }}
      >
        <div className="eyebrow" style={{ marginBottom: '8px' }}>Look up a farmer</div>
        <div className="flex gap-2">
          <input
            value={farmerPhone}
            onChange={e => setFarmerPhone(e.target.value)}
            placeholder="+919876543210"
            onKeyDown={e => e.key === 'Enter' && lookupFarmer(farmerPhone)}
            aria-label="Farmer phone number"
            className="input"
            style={{ flex: 1 }}
          />
          <button
            onClick={() => lookupFarmer(farmerPhone)}
            disabled={lookingUp}
            className="btn-primary"
            style={{ padding: '6px 14px', fontSize: '13px' }}
          >
            <Search size={12} />
            {lookingUp ? '…' : 'Look up'}
          </button>
        </div>

        {farmerInfo && (
          <div style={{ marginTop: '10px', fontSize: '13px', color: '#606373' }}>
            <strong style={{ color: '#1b1e2d' }}>{farmerInfo.name}</strong> · {farmerInfo.district}, {farmerInfo.state}<br />
            Crops: {farmerInfo.crops.join(', ')} · {farmerInfo.area.toFixed(1)} ha
          </div>
        )}

        <button
          onClick={() => setShowDemoFarmers(!showDemoFarmers)}
          className="text-link"
          style={{ marginTop: '10px', fontSize: '12px' }}
        >
          {showDemoFarmers ? 'Hide examples' : 'Try a demo farmer'}
        </button>

        {showDemoFarmers && farmers.data && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginTop: '6px' }}>
            {farmers.data.slice(0, 6).map(f => (
              <button
                key={f.phone}
                onClick={() => selectDemoFarmer(f)}
                className="chip"
                style={{ fontSize: '12px', padding: '4px 10px' }}
              >
                {f.name} ({f.phone.slice(-4)})
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Messages */}
      <div
        className="flex-1 overflow-y-auto flex flex-col"
        style={{ padding: '16px 20px', gap: '20px' }}
      >
        {messages.map((msg, i) => (
          <div key={i}>
            <div
              className="eyebrow"
              style={{ marginBottom: '6px', fontSize: '11px' }}
            >
              {msg.role === 'user' ? 'You' : 'Model'}
            </div>
            <div
              style={{
                fontFamily:
                  msg.role === 'user'
                    ? '"Space Grotesk", system-ui, sans-serif'
                    : '"Source Serif 4", Georgia, serif',
                fontSize: msg.role === 'user' ? '13px' : '15px',
                lineHeight: 1.65,
                color: '#1b1e2d',
              }}
            >
              <span
                dangerouslySetInnerHTML={{ __html: renderMarkdown(msg.content) }}
              />
            </div>
          </div>
        ))}
        {sending && (
          <div className="flex items-center gap-1">
            <span className="typing-dot" />
            <span className="typing-dot" />
            <span className="typing-dot" />
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div
        className="flex gap-2 shrink-0"
        style={{
          padding: '12px 20px',
          borderTop: '1px solid #e8e5e1',
          background: '#fcfaf7',
        }}
      >
        <input
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && !e.shiftKey && sendMessage()}
          placeholder="Ask a question..."
          disabled={sending}
          aria-label="Chat message input"
          className="input"
          style={{ flex: 1 }}
        />
        <button
          onClick={sendMessage}
          disabled={sending || !input.trim()}
          aria-label="Send message"
          className="btn-primary"
          style={{
            padding: '6px 12px',
            opacity: sending || !input.trim() ? 0.5 : 1,
          }}
        >
          <Send size={14} />
        </button>
        <button
          onClick={clearChat}
          title="Clear conversation"
          aria-label="Clear conversation"
          className="btn-secondary"
          style={{ padding: '6px 10px' }}
        >
          <Trash2 size={14} />
        </button>
      </div>
    </div>
  )
}
