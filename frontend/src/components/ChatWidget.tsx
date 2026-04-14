import { useState, useRef, useEffect } from 'react'
import { MessageCircle, X, Send, Search, Trash2 } from 'lucide-react'
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
    "Welcome! I can explain how this weather system works, show you forecasts for any station, " +
    "or answer questions about the technology. Try: 'How are forecasts generated?', " +
    "'Show the latest data for Chennai', or 'What technology powers this?'",
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
        title="Open Chat"
        className="fixed bottom-6 right-6 z-[1000] w-[52px] h-[52px] rounded-full bg-gold text-white border-0 cursor-pointer shadow-[0_4px_16px_rgba(212,160,25,0.4)] flex items-center justify-center transition-transform hover:scale-[1.08]"
      >
        <MessageCircle size={22} />
      </button>
    )
  }

  return (
    <div className="chat-widget-container fixed bottom-6 right-6 z-[1000] w-[380px] max-w-[calc(100vw-48px)] h-[600px] max-h-[calc(100vh-48px)] bg-cream rounded-xl border border-warm-border shadow-[0_8px_32px_rgba(0,0,0,0.15)] flex flex-col overflow-hidden">
      <style>{`
        .chat-widget-container code {
          background: #f5f3ef;
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
      <div className="bg-sidebar text-white px-4 py-[14px] flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2">
          <MessageCircle size={16} />
          <span className="font-semibold text-[0.88rem]">Farmer Advisor Chat</span>
        </div>
        <button
          onClick={() => setOpen(false)}
          aria-label="Close chat"
          className="bg-transparent border-0 text-[#aaa] cursor-pointer p-0.5 flex hover:text-white"
        >
          <X size={18} />
        </button>
      </div>

      {/* Farmer Identity */}
      <div className="px-[14px] py-[10px] border-b border-warm-border bg-warm-header-bg shrink-0">
        <div className="text-[0.72rem] font-semibold text-warm-muted uppercase tracking-label mb-1.5">
          Farmer Identity
        </div>
        <div className="flex gap-1.5">
          <input
            value={farmerPhone}
            onChange={e => setFarmerPhone(e.target.value)}
            placeholder="+919876543210"
            onKeyDown={e => e.key === 'Enter' && lookupFarmer(farmerPhone)}
            aria-label="Farmer phone number"
            className="flex-1 px-[10px] py-1.5 text-[0.82rem] border border-warm-border rounded-md bg-white outline-none text-[#1a1a1a]"
          />
          <button
            onClick={() => lookupFarmer(farmerPhone)}
            disabled={lookingUp}
            className="px-[10px] py-1.5 text-[0.75rem] font-semibold bg-gold text-white border-0 rounded-md cursor-pointer flex items-center gap-1"
          >
            <Search size={12} />
            {lookingUp ? '...' : 'Look up'}
          </button>
        </div>

        {farmerInfo && (
          <div className="mt-1.5 text-[0.78rem] text-warm-body">
            <strong>{farmerInfo.name}</strong> · {farmerInfo.district}, {farmerInfo.state}<br />
            Crops: {farmerInfo.crops.join(', ')} · {farmerInfo.area.toFixed(1)} ha
          </div>
        )}

        <button
          onClick={() => setShowDemoFarmers(!showDemoFarmers)}
          className="mt-1.5 bg-transparent border-0 text-gold text-[0.72rem] cursor-pointer p-0 underline"
        >
          {showDemoFarmers ? 'Hide' : 'Demo farmers'}
        </button>

        {showDemoFarmers && farmers.data && (
          <div className="mt-1 flex flex-wrap gap-1">
            {farmers.data.slice(0, 6).map(f => (
              <button
                key={f.phone}
                onClick={() => selectDemoFarmer(f)}
                className="bg-white border border-warm-border rounded px-2 py-[3px] text-[0.7rem] cursor-pointer text-warm-body"
              >
                {f.name} ({f.phone.slice(-4)})
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-[14px] py-3 flex flex-col gap-2.5">
        {messages.map((msg, i) => (
          <div
            key={i}
            className={`flex flex-col ${msg.role === 'user' ? 'items-end' : 'items-start'}`}
          >
            <div
              className={`max-w-[85%] px-3 py-2 rounded-[10px] text-[0.82rem] leading-[1.5] ${
                msg.role === 'user'
                  ? 'bg-gold text-white border-0'
                  : 'bg-white text-[#1a1a1a] border border-warm-border'
              }`}
            >
              <span dangerouslySetInnerHTML={{ __html: renderMarkdown(msg.content) }} />
            </div>
          </div>
        ))}
        {sending && (
          <div className="flex items-center gap-1 px-3 py-2">
            <span className="typing-dot" />
            <span className="typing-dot" />
            <span className="typing-dot" />
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="px-[14px] py-2.5 border-t border-warm-border bg-warm-header-bg flex gap-1.5 shrink-0">
        <input
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && !e.shiftKey && sendMessage()}
          placeholder="Ask something..."
          disabled={sending}
          aria-label="Chat message input"
          className="flex-1 px-3 py-2 text-[0.82rem] border border-warm-border rounded-lg bg-white outline-none text-[#1a1a1a]"
        />
        <button
          onClick={sendMessage}
          disabled={sending || !input.trim()}
          aria-label="Send message"
          className={`px-3 py-2 bg-gold text-white border-0 rounded-lg cursor-pointer flex items-center ${
            sending || !input.trim() ? 'opacity-50' : ''
          }`}
        >
          <Send size={14} />
        </button>
        <button
          onClick={clearChat}
          title="Clear conversation"
          aria-label="Clear conversation"
          className="p-2 bg-transparent border border-warm-border rounded-lg cursor-pointer flex items-center text-warm-muted"
        >
          <Trash2 size={14} />
        </button>
      </div>
    </div>
  )
}
