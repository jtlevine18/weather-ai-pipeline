import { useState, useRef, useEffect } from 'react'
import { MessageCircle, X, Send, Search, Trash2 } from 'lucide-react'
import { apiFetch } from '../api/client'
import { useFarmers } from '../api/hooks'
import type { FarmerSummary } from '../api/hooks'

interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

const INITIAL_MSG: ChatMessage = {
  role: 'assistant',
  content:
    "Welcome! I can explain any part of this AI weather pipeline, show you live data, " +
    "or walk you through the architecture. Try asking: 'How does NeuralGCM work?', " +
    "'Show me the latest forecast for Chennai', or 'What's the tech stack?'",
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
      if (saved) return JSON.parse(saved)
    } catch {}
    return [INITIAL_MSG]
  })
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [farmerPhone, setFarmerPhone] = useState('')
  const [farmerInfo, setFarmerInfo] = useState<{ name: string; district: string; state: string; crops: string[]; area: number } | null>(null)
  const [lookingUp, setLookingUp] = useState(false)
  const [showDemoFarmers, setShowDemoFarmers] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const farmers = useFarmers({ enabled: open })

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    try { sessionStorage.setItem('weather_chat_messages', JSON.stringify(messages)) } catch {}
  }, [messages])

  async function lookupFarmer(phone: string) {
    if (!phone.trim()) return
    setLookingUp(true)
    try {
      const detail: any = await apiFetch(`/api/farmers/${encodeURIComponent(phone.trim())}`)
      const info = {
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
    } catch {
      setMessages(prev => [...prev, { role: 'assistant', content: 'No farmer found with that phone number.' }])
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
      const resp: any = await apiFetch('/api/chat', {
        method: 'POST',
        body: JSON.stringify({
          message: userMsg,
          history: messages.slice(-10),
          farmer_phone: farmerPhone || undefined,
        }),
      })
      setMessages(prev => [...prev, { role: 'assistant', content: resp.response || 'No response.' }])
    } catch (err: any) {
      setMessages(prev => [...prev, { role: 'assistant', content: `Error: ${err.message || 'Unknown error'}` }])
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
        style={{
          position: 'fixed', bottom: '24px', right: '24px', zIndex: 1000,
          width: '52px', height: '52px', borderRadius: '50%',
          background: '#d4a019', color: '#fff', border: 'none', cursor: 'pointer',
          boxShadow: '0 4px 16px rgba(212, 160, 25, 0.4)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          transition: 'transform 0.15s, box-shadow 0.15s',
        }}
        onMouseEnter={e => { e.currentTarget.style.transform = 'scale(1.08)' }}
        onMouseLeave={e => { e.currentTarget.style.transform = 'scale(1)' }}
        title="Open Chat"
      >
        <MessageCircle size={22} />
      </button>
    )
  }

  return (
    <div className="chat-widget-container" style={{
      position: 'fixed', bottom: '24px', right: '24px', zIndex: 1000,
      width: '380px', maxWidth: 'calc(100vw - 48px)',
      height: '600px', maxHeight: 'calc(100vh - 48px)',
      background: '#faf8f5', borderRadius: '12px',
      border: '1px solid #e0dcd5',
      boxShadow: '0 8px 32px rgba(0,0,0,0.15)',
      display: 'flex', flexDirection: 'column',
      overflow: 'hidden',
    }}>
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
      <div style={{
        background: '#1a1a1a', color: '#fff',
        padding: '14px 16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        flexShrink: 0,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <MessageCircle size={16} />
          <span style={{ fontWeight: 600, fontSize: '0.88rem' }}>Weather AI Chat</span>
        </div>
        <button onClick={() => setOpen(false)} style={{
          background: 'none', border: 'none', color: '#aaa', cursor: 'pointer',
          padding: '2px', display: 'flex',
        }}>
          <X size={18} />
        </button>
      </div>

      {/* Farmer Identity */}
      <div style={{
        padding: '10px 14px', borderBottom: '1px solid #e0dcd5',
        background: '#f5f3ef', flexShrink: 0,
      }}>
        <div style={{ fontSize: '0.72rem', fontWeight: 600, color: '#888', textTransform: 'uppercase', letterSpacing: '1px', marginBottom: '6px' }}>
          Farmer Identity
        </div>
        <div style={{ display: 'flex', gap: '6px' }}>
          <input
            value={farmerPhone}
            onChange={e => setFarmerPhone(e.target.value)}
            placeholder="+919876543210"
            onKeyDown={e => e.key === 'Enter' && lookupFarmer(farmerPhone)}
            style={{
              flex: 1, padding: '6px 10px', fontSize: '0.82rem',
              border: '1px solid #e0dcd5', borderRadius: '6px', background: '#fff',
              outline: 'none', color: '#1a1a1a',
            }}
          />
          <button
            onClick={() => lookupFarmer(farmerPhone)}
            disabled={lookingUp}
            style={{
              padding: '6px 10px', fontSize: '0.75rem', fontWeight: 600,
              background: '#d4a019', color: '#fff', border: 'none',
              borderRadius: '6px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '4px',
            }}
          >
            <Search size={12} />
            {lookingUp ? '...' : 'Look up'}
          </button>
        </div>

        {farmerInfo && (
          <div style={{ marginTop: '6px', fontSize: '0.78rem', color: '#555' }}>
            <strong>{farmerInfo.name}</strong> · {farmerInfo.district}, {farmerInfo.state}<br />
            Crops: {farmerInfo.crops.join(', ')} · {farmerInfo.area.toFixed(1)} ha
          </div>
        )}

        <button
          onClick={() => setShowDemoFarmers(!showDemoFarmers)}
          style={{
            marginTop: '6px', background: 'none', border: 'none',
            color: '#d4a019', fontSize: '0.72rem', cursor: 'pointer',
            padding: 0, textDecoration: 'underline',
          }}
        >
          {showDemoFarmers ? 'Hide' : 'Demo farmers'}
        </button>

        {showDemoFarmers && farmers.data && (
          <div style={{ marginTop: '4px', display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
            {farmers.data.slice(0, 6).map(f => (
              <button
                key={f.phone}
                onClick={() => selectDemoFarmer(f)}
                style={{
                  background: '#fff', border: '1px solid #e0dcd5', borderRadius: '4px',
                  padding: '3px 8px', fontSize: '0.7rem', cursor: 'pointer',
                  color: '#555',
                }}
              >
                {f.name} ({f.phone.slice(-4)})
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Messages */}
      <div style={{
        flex: 1, overflowY: 'auto', padding: '12px 14px',
        display: 'flex', flexDirection: 'column', gap: '10px',
      }}>
        {messages.map((msg, i) => (
          <div key={i} style={{
            display: 'flex', flexDirection: 'column',
            alignItems: msg.role === 'user' ? 'flex-end' : 'flex-start',
          }}>
            <div style={{
              maxWidth: '85%', padding: '8px 12px', borderRadius: '10px',
              fontSize: '0.82rem', lineHeight: 1.5,
              background: msg.role === 'user' ? '#d4a019' : '#fff',
              color: msg.role === 'user' ? '#fff' : '#1a1a1a',
              border: msg.role === 'user' ? 'none' : '1px solid #e0dcd5',
            }}>
              <span dangerouslySetInnerHTML={{ __html: renderMarkdown(msg.content) }} />
            </div>
          </div>
        ))}
        {sending && (
          <div style={{
            display: 'flex', alignItems: 'center', gap: '4px',
            padding: '8px 12px',
          }}>
            <span className="typing-dot" />
            <span className="typing-dot" />
            <span className="typing-dot" />
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div style={{
        padding: '10px 14px', borderTop: '1px solid #e0dcd5',
        background: '#f5f3ef', display: 'flex', gap: '6px',
        flexShrink: 0,
      }}>
        <input
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && !e.shiftKey && sendMessage()}
          placeholder="Ask something..."
          disabled={sending}
          style={{
            flex: 1, padding: '8px 12px', fontSize: '0.82rem',
            border: '1px solid #e0dcd5', borderRadius: '8px', background: '#fff',
            outline: 'none', color: '#1a1a1a',
          }}
        />
        <button
          onClick={sendMessage}
          disabled={sending || !input.trim()}
          style={{
            padding: '8px 12px', background: '#d4a019', color: '#fff',
            border: 'none', borderRadius: '8px', cursor: 'pointer',
            display: 'flex', alignItems: 'center',
            opacity: sending || !input.trim() ? 0.5 : 1,
          }}
        >
          <Send size={14} />
        </button>
        <button
          onClick={clearChat}
          style={{
            padding: '8px', background: 'none', border: '1px solid #e0dcd5',
            borderRadius: '8px', cursor: 'pointer', display: 'flex', alignItems: 'center',
            color: '#888',
          }}
          title="Clear conversation"
        >
          <Trash2 size={14} />
        </button>
      </div>
    </div>
  )
}
