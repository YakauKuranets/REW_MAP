import React, { useEffect, useMemo, useRef, useState } from 'react';
import useMapStore from '../store/useMapStore';

const SEND_ENDPOINT = process.env.REACT_APP_INCIDENT_CHAT_SEND_URL || '/api/chat/incident';

function normalizeMessage(message, index) {
  const text = message?.text || message?.message || '';
  const role = (message?.sender || message?.role || '').toLowerCase();
  const isDispatcher = role === 'dispatcher' || role === 'admin' || role === 'command';

  return {
    id: message?.id || message?.message_id || `${Date.now()}-${index}`,
    text,
    role,
    author: message?.author || (isDispatcher ? 'Диспетчер' : 'Агент'),
    at: message?.created_at || message?.timestamp,
    isDispatcher,
  };
}

export default function IncidentChat() {
  const chatMessages = useMapStore((s) => s.chatMessages);
  const addChatMessage = useMapStore((s) => s.addChatMessage);
  const [isOpen, setIsOpen] = useState(true);
  const [draft, setDraft] = useState('');
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState('');
  const viewportRef = useRef(null);

  const preparedMessages = useMemo(
    () => chatMessages.map((msg, index) => normalizeMessage(msg, index)).filter((msg) => msg.text),
    [chatMessages],
  );

  useEffect(() => {
    if (!viewportRef.current) return;
    viewportRef.current.scrollTo({
      top: viewportRef.current.scrollHeight,
      behavior: 'smooth',
    });
  }, [preparedMessages.length]);

  const submitMessage = async (event) => {
    event.preventDefault();
    const text = draft.trim();
    if (!text || isSending) return;

    setIsSending(true);
    setError('');

    try {
      const response = await fetch(SEND_ENDPOINT, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, sender: 'dispatcher' }),
      });

      if (!response.ok) {
        throw new Error(`Request failed with status ${response.status}`);
      }

      const saved = await response.json();
      addChatMessage(saved);
      setDraft('');
    } catch (_e) {
      setError('Не удалось отправить сообщение.');
    } finally {
      setIsSending(false);
    }
  };

  return (
    <>
      <button
        type="button"
        onClick={() => setIsOpen((prev) => !prev)}
        className="absolute right-4 top-4 z-40 rounded-md border border-cyan-400/40 bg-black/70 px-3 py-2 text-xs uppercase tracking-wider text-cyan-300"
      >
        {isOpen ? 'Скрыть чат' : 'Открыть чат'}
      </button>

      <aside
        className={`absolute right-0 top-0 z-30 h-full w-96 border-l border-white/10 bg-black/60 backdrop-blur-md transition-transform duration-300 ${
          isOpen ? 'translate-x-0' : 'translate-x-full'
        }`}
      >
        <div className="flex h-full flex-col">
          <div className="border-b border-white/10 px-4 py-3 text-sm font-semibold text-cyan-200">Incident Chat</div>

          <div ref={viewportRef} className="flex-1 space-y-3 overflow-y-auto px-4 py-3">
            {preparedMessages.map((msg) => (
              <div key={msg.id} className={`rounded-lg border px-3 py-2 text-sm ${msg.isDispatcher ? 'border-cyan-400/30 bg-cyan-500/10 text-cyan-200 shadow-[0_0_12px_rgba(34,211,238,0.25)]' : 'border-slate-500/30 bg-slate-700/30 text-slate-200'}`}>
                <div className="mb-1 text-xs opacity-80">{msg.author}</div>
                <div>{msg.text}</div>
              </div>
            ))}
          </div>

          <form onSubmit={submitMessage} className="space-y-2 border-t border-white/10 p-3">
            <input
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              placeholder="Сообщение в инцидент..."
              className="w-full rounded-md border border-white/20 bg-slate-900/60 px-3 py-2 text-sm text-slate-100 outline-none focus:border-cyan-400/70"
            />
            {error ? <div className="text-xs text-red-300">{error}</div> : null}
            <button
              type="submit"
              disabled={isSending || !draft.trim()}
              className="w-full rounded-md bg-cyan-500 px-3 py-2 text-sm font-medium text-slate-950 disabled:cursor-not-allowed disabled:bg-cyan-900"
            >
              {isSending ? 'Отправка...' : 'Отправить'}
            </button>
          </form>
        </div>
      </aside>
    </>
  );
}
