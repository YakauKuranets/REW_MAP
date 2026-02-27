import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Send, X } from 'lucide-react';
import useChatStore from '../store/useChatStore';

/**
 * Sliding incident chat panel (cyber-glass style).
 * @param {{incidentId: string | number, onClose?: () => void}} props
 * @returns {JSX.Element | null}
 */
export default function IncidentChatPanel({ incidentId, onClose }) {
  const messagesByIncident = useChatStore((s) => s.messagesByIncident);
  const [draft, setDraft] = useState('');
  const [isSending, setIsSending] = useState(false);
  const bottomRef = useRef(null);

  const normalizedIncidentId = useMemo(
    () => (incidentId === undefined || incidentId === null ? null : String(incidentId)),
    [incidentId],
  );

  const messages = normalizedIncidentId ? (messagesByIncident[normalizedIncidentId] || []) : [];

  useEffect(() => {
    if (!bottomRef.current) return;
    bottomRef.current.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  if (!normalizedIncidentId) return null;

  const sendMessage = async () => {
    const text = draft.trim();
    if (!text || isSending) return;

    // Clear instantly. WS echo will append the persisted message.
    setDraft('');
    setIsSending(true);

    try {
      await fetch(`/api/incidents/${normalizedIncidentId}/chat/send`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text,
          author_id: 'dispatcher-ui',
        }),
      });
    } catch (_error) {
      // Network failures are intentionally non-blocking for input UX.
    } finally {
      setIsSending(false);
    }
  };

  const handleSubmit = (event) => {
    event.preventDefault();
    sendMessage();
  };

  const handleInputKeyDown = (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      sendMessage();
    }
  };

  return (
    <aside className="fixed right-0 top-16 z-50 flex h-[calc(100vh-4rem)] w-96 flex-col border-l border-cyan-500/30 bg-black/60 backdrop-blur-xl shadow-[0_0_30px_rgba(0,255,255,0.1)]">
      <header className="flex items-center justify-between border-b border-cyan-500/30 px-4 py-3">
        <div>
          <div className="text-[11px] uppercase tracking-widest text-cyan-300/80">Incident Channel</div>
          <h3 className="text-sm font-semibold text-cyan-100">Инцидент #{normalizedIncidentId}</h3>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="rounded-md border border-cyan-500/40 bg-cyan-900/20 p-1.5 text-cyan-200 transition hover:bg-cyan-800/40"
          aria-label="Закрыть чат"
        >
          <X className="h-4 w-4" />
        </button>
      </header>

      <div className="chat-scroll flex-1 space-y-4 overflow-y-auto p-4">
        {messages.map((msg, index) => {
          const key = String(msg?.id ?? `${normalizedIncidentId}-${index}`);
          const role = String(msg?.role || '').toLowerCase();

          if (role === 'system') {
            const isAlert = /error|alert|critical|alarm|danger/i.test(String(msg?.text || ''));
            return (
              <div key={key} className={`mx-auto max-w-[90%] text-center text-xs font-semibold ${isAlert ? 'animate-pulse text-red-300' : 'animate-pulse text-yellow-300'}`}>
                {msg?.text || ''}
              </div>
            );
          }

          const isDispatcher = role === 'dispatcher';
          return (
            <div
              key={key}
              className={`max-w-[85%] rounded-xl px-3 py-2 text-sm ${isDispatcher ? 'ml-auto self-end border border-cyan-500/50 bg-cyan-900/40 text-cyan-100' : 'mr-auto self-start border border-gray-600/50 bg-gray-800/60 text-white'}`}
            >
              <div className="mb-1 text-[10px] uppercase tracking-wider opacity-75">{msg?.author || (isDispatcher ? 'Dispatcher' : 'Agent')}</div>
              <div>{msg?.text || ''}</div>
            </div>
          );
        })}
        <div ref={bottomRef} />
      </div>

      <form onSubmit={handleSubmit} className="border-t border-cyan-500/30 bg-black/50 p-4">
        <div className="flex items-center gap-2">
          <input
            type="text"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={handleInputKeyDown}
            placeholder="Отправить сообщение диспетчера..."
            className="h-10 flex-1 rounded-md border border-cyan-500/40 bg-black/60 px-3 text-sm text-cyan-100 outline-none placeholder:text-cyan-400/40 focus:border-cyan-300"
          />
          <button
            type="submit"
            disabled={!draft.trim() || isSending}
            className="inline-flex h-10 w-10 items-center justify-center rounded-md border border-cyan-400/50 bg-cyan-500/20 text-cyan-100 transition hover:bg-cyan-400/30 disabled:cursor-not-allowed disabled:opacity-50"
            aria-label="Отправить"
          >
            <Send className="h-4 w-4" />
          </button>
        </div>
      </form>
    </aside>
  );
}
