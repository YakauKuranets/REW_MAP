import React, { useEffect, useState } from 'react';
import { Cpu, Activity, ShieldCheck, Satellite } from 'lucide-react';
import useMapStore from '../store/useMapStore';

function StatusPill({ label, online = true }) {
  return (
    <div className="flex items-center gap-2 rounded-full border border-white/10 bg-black/30 px-3 py-1.5 text-[10px] uppercase tracking-wider text-slate-200">
      <span className={`h-2 w-2 rounded-full ${online ? 'bg-emerald-400' : 'bg-neon-red'}`} />
      <span className="opacity-80">{label}</span>
    </div>
  );
}

export default function TopBar() {
  const agents = useMapStore((s) => s.agents);
  const pendingMarkers = useMapStore((s) => s.pendingMarkers);
  const activeAgents = Object.keys(agents || {}).length;
  const pendingCount = pendingMarkers.length;
  const [isOnline, setIsOnline] = useState(() => (typeof navigator === 'undefined' ? true : navigator.onLine));

  useEffect(() => {
    const onOnline = () => setIsOnline(true);
    const onOffline = () => setIsOnline(false);

    window.addEventListener('online', onOnline);
    window.addEventListener('offline', onOffline);

    return () => {
      window.removeEventListener('online', onOnline);
      window.removeEventListener('offline', onOffline);
    };
  }, []);

  return (
    <div className="pointer-events-auto absolute left-0 right-0 top-0 z-50 border-b border-white/10 bg-black/40 backdrop-blur-md">
      <div className="flex h-14 items-center justify-between px-4 md:px-6">
        <div className="flex items-center gap-3 text-cyber-blue">
          <ShieldCheck className="h-5 w-5" />
          <span className="text-sm font-black uppercase tracking-[0.2em]">Command Center v4.0</span>
        </div>

        <div className="hidden items-center gap-2 md:flex">
          <StatusPill label="Rust Gateway" online />
          <StatusPill label="Redis Bridge" online />
          <StatusPill label="WebSocket" online />
        </div>

        <div className="flex items-center gap-3">
          <div className={`flex items-center gap-2 rounded-xl border px-3 py-1.5 ${isOnline ? 'border-emerald-400/40 bg-emerald-500/10 text-emerald-300' : 'border-red-400/60 bg-red-900/30 text-red-300 animate-pulse'}`}>
            <Satellite className="h-4 w-4" />
            <span className="text-xs font-bold uppercase tracking-wider">{isOnline ? '[GRID: ONLINE]' : '[GRID: ISOLATED (OFFLINE)]'}</span>
          </div>

          <div className="flex items-center gap-2 rounded-xl border border-yellow-300/40 bg-yellow-300/10 px-3 py-1.5 text-yellow-200">
            <span className={`h-2.5 w-2.5 rounded-full ${pendingCount > 0 ? 'animate-pulse bg-yellow-300 shadow-[0_0_12px_rgba(252,211,77,0.9)]' : 'bg-yellow-200/50'}`} />
            <span className="text-xs font-bold uppercase tracking-wider">Входящие сигналы: {pendingCount}</span>
          </div>

          <div className="flex items-center gap-2 rounded-xl border border-cyber-blue/30 bg-cyber-blue/10 px-3 py-1.5 text-cyber-blue shadow-neon">
            <Activity className="h-4 w-4" />
            <span className="text-xs font-bold uppercase tracking-wider">Agents: {activeAgents}</span>
            <Cpu className="h-4 w-4 opacity-80" />
          </div>
        </div>
      </div>
    </div>
  );
}
