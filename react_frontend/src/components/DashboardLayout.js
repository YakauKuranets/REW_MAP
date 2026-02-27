import React from 'react';
import { Map, Users, Settings, Plus } from 'lucide-react';
import TopBar from './TopBar';
import CTIConsole from './CTIConsole';
import IdentityGraphPanel from './IdentityGraphPanel';
import useMapStore from '../store/useMapStore';


const mockData = {
  alias: 'apt-ghost',
  connections: [
    { entity: 'bc1q7x...f93k', type: 'CRYPTO_WALLET', relation: 'RECEIVED_FUNDS' },
    { entity: 'UTC+3 (based on activity hours and slang)', type: 'TIMEZONE', relation: 'OPERATES_IN' },
    { entity: '0xDEADBEEF_PGP', type: 'PGP_KEY', relation: 'SIGNED_WITH' },
  ],
};

function NavButton({ active, icon, label, onClick }) {
  return (
    <button
      onClick={onClick}
      className={`flex w-full items-center gap-3 rounded-xl border px-3 py-2 text-left text-xs font-bold uppercase tracking-wider transition ${
        active
          ? 'border-cyber-blue/50 bg-cyber-blue/20 text-cyber-blue shadow-neon'
          : 'border-white/10 bg-black/30 text-slate-300 hover:border-cyber-blue/30 hover:text-cyber-blue'
      }`}
    >
      {icon}
      <span>{label}</span>
    </button>
  );
}

export default function DashboardLayout({ children, activeTab, onTabChange }) {
  const setDraftMarker = useMapStore((s) => s.setDraftMarker);

  const handleManualAdd = () => {
    setDraftMarker({
      lon: 27.56,
      lat: 53.9,
      address: '',
      title: '',
      description: '',
      url: '',
      image: '',
      cameraType: 'remote',
    });
  };

  return (
    <div className="relative h-screen w-full overflow-hidden bg-black text-slate-100">
      {children}

      <IdentityGraphPanel actorData={mockData} />

      <div className="pointer-events-none absolute inset-0 z-40">
        <TopBar />

        <aside className="pointer-events-auto absolute left-4 top-20 w-56 rounded-2xl border border-white/10 bg-black/40 p-3 backdrop-blur-cyber">
          <div className="mb-3 text-[10px] font-black uppercase tracking-[0.25em] text-cyber-blue">Cyber Panel</div>
          <div className="space-y-2">
            <NavButton active={activeTab === 'radar'} onClick={() => onTabChange('radar')} icon={<Map className="h-4 w-4" />} label="Radar" />
            <NavButton active={activeTab === 'agents'} onClick={() => onTabChange('agents')} icon={<Users className="h-4 w-4" />} label="Agents" />
            <NavButton active={activeTab === 'settings'} onClick={() => onTabChange('settings')} icon={<Settings className="h-4 w-4" />} label="Settings" />
          </div>

          <CTIConsole />

          <button
            onClick={handleManualAdd}
            className="mt-3 flex w-full items-center justify-center gap-2 rounded-xl border border-alert-yellow/40 bg-alert-yellow/10 px-3 py-2 text-xs font-bold uppercase tracking-wider text-alert-yellow transition hover:bg-alert-yellow/20"
          >
            <Plus className="h-4 w-4" />
            Add Object
          </button>
        </aside>
      </div>
    </div>
  );
}
