import React from 'react';
import { Cctv, X } from 'lucide-react';

export default function TacticalGridDashboard({ terminal, onClose }) {
  if (!terminal) return null;

  const channels = Array.isArray(terminal.channels) ? terminal.channels : [];
  const activeChannelsCount = channels.filter((channel) => channel?.status === 'online').length;
  const gridColsClass = channels.length > 4 ? 'grid-cols-3' : 'grid-cols-2';

  return (
    <div className="absolute inset-0 z-50 bg-slate-900/90 backdrop-blur-md p-6 flex flex-col">
      <div className="mb-4 flex items-start justify-between gap-4 border-b border-cyan-500/30 pb-4">
        <div className="space-y-1">
          <div className="font-mono text-xl uppercase tracking-wider text-cyan-300">
            {terminal.name || 'UNKNOWN TERMINAL'}
          </div>
          <div className="font-mono text-xs text-cyan-100/80">
            IP: {terminal.ip || terminal.ip_address || 'N/A'}
          </div>
        </div>

        <div className="flex items-center gap-3">
          <span className="rounded-full border border-cyan-400/50 bg-cyan-500/10 px-3 py-1 font-mono text-xs uppercase tracking-wide text-cyan-200">
            Active channels: {activeChannelsCount}
          </span>
          <button
            type="button"
            onClick={onClose}
            className="inline-flex items-center gap-2 rounded border border-red-500/50 bg-red-500/10 px-3 py-1 font-mono text-xs uppercase tracking-wide text-red-300 transition hover:text-red-500"
          >
            <X className="h-4 w-4" />
            Close
          </button>
        </div>
      </div>

      <div className={`grid flex-1 gap-4 overflow-auto ${gridColsClass}`}>
        {channels.map((channel, index) => (
          <article
            key={channel?.id || `${channel?.name || 'channel'}-${index}`}
            className="relative overflow-hidden rounded-xl border border-cyan-500/25 bg-black/40 p-3 shadow-[0_0_20px_rgba(6,182,212,0.15)]"
          >
            <div className="mb-2 font-mono text-xs uppercase tracking-wide text-cyan-200">
              CH_{index + 1} // {channel?.name || 'Unnamed channel'}
            </div>

            {channel?.terminal_type === 'LEGACY_FTP' ? (
              <div className="flex h-56 flex-col items-center justify-center rounded-lg border border-yellow-500/40 bg-yellow-900/10 text-yellow-200">
                <Cctv className="mb-3 h-9 w-9" />
                <button
                  type="button"
                  className="rounded border border-yellow-400/70 bg-yellow-500/10 px-4 py-2 font-mono text-[11px] uppercase tracking-wide text-yellow-300 shadow-[0_0_16px_rgba(234,179,8,0.35)] transition hover:bg-yellow-500/20"
                >
                  [ ЗАПРОСИТЬ АРХИВ ИЗ FTP ]
                </button>
              </div>
            ) : channel?.status === 'online' ? (
              <img
                src={`/api/proxy/stream/${channel?.id}`}
                alt={`Live stream ${channel?.name || index + 1}`}
                className="h-56 w-full rounded-lg border border-cyan-700 object-cover"
              />
            ) : (
              <div className="flex h-56 items-center justify-center rounded-lg border border-slate-700 bg-slate-950/70 font-mono text-xs uppercase tracking-[0.2em] text-slate-400">
                Channel offline
              </div>
            )}
          </article>
        ))}
      </div>
    </div>
  );
}
