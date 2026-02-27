import React, { useState, useMemo } from 'react';
import DashboardLayout from '../components/DashboardLayout';
import CommandCenterMap from '../components/CommandCenterMap';
import IncidentFeed from '../components/IncidentFeed';
import VideoModal from '../components/VideoModal';
import ObjectInspector from '../components/ObjectInspector';
import IncidentChat from '../components/IncidentChat';
import IncidentChatPanel from '../components/IncidentChatPanel';
import PendingRequestsPanel from '../components/PendingRequestsPanel';
import SmartFilterPanel from '../components/SmartFilterPanel';
import CyberHUD from '../components/CyberHUD';
import AssetRiskGraphPanel from '../components/AssetRiskGraphPanel';
import useMapStore from '../store/useMapStore';

export default function Dashboard() {
  const [activeObjectId, setActiveObjectId] = useState(null);
  const [activeNode, setActiveNode] = useState(null);
  const [activeTab, setActiveTab] = useState('radar');
  const [theme, setTheme] = useState('dark');
  const [flyToTarget, setFlyToTarget] = useState(null);
  const [activeChatIncidentId, setActiveChatIncidentId] = useState(null);
  const [assetRiskData] = useState({ nodes: [], edges: [] });
  const [filters, setFilters] = useState({
    showAgents: true,
    showCameras: true,
    showIncidents: true,
    showPending: true,
  });

  const trackers = useMapStore((s) => s.trackers);

  const selectedObjectData = useMemo(() => {
    if (!activeObjectId || !trackers[activeObjectId]) return null;
    return { id: activeObjectId, ...trackers[activeObjectId] };
  }, [activeObjectId, trackers]);

  const bgClass = theme === 'dark' ? 'bg-slate-950' : 'bg-slate-100';

  const renderContent = () => {
    switch (activeTab) {
      case 'radar':
        return (
          <>
            <div className="absolute inset-0">
              <CommandCenterMap
                theme={theme}
                flyToTarget={flyToTarget}
                onToggleTheme={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
                onUserClick={(id) => setActiveObjectId(id)}
                setActiveNode={setActiveNode}
                filters={filters}
              />
            </div>
            <IncidentFeed theme={theme} />
            <IncidentChat />
            <PendingRequestsPanel onFlyToPending={setFlyToTarget} />
            <SmartFilterPanel filters={filters} onFiltersChange={setFilters} />
          </>
        );
      case 'agents':
        return <div className={`p-10 ${theme === 'dark' ? 'text-slate-400' : 'text-slate-500'}`}>Раздел списка сотрудников (в разработке)</div>;
      case 'analytics':
        return (
          <div className="p-6">
            <h2 className={`mb-4 font-mono text-sm ${theme === 'dark' ? 'text-cyan-300' : 'text-slate-700'}`}>ASSET RISK GRAPH</h2>
            <AssetRiskGraphPanel riskData={assetRiskData} />
          </div>
        );
      default:
        return null;
    }
  };

  return (
    <DashboardLayout activeTab={activeTab} onTabChange={setActiveTab} theme={theme} activeNode={activeNode}>
      <div className={`relative h-full w-full transition-colors duration-500 ${bgClass}`}>
        {renderContent()}


        {activeChatIncidentId !== null && (
          <IncidentChatPanel
            incidentId={activeChatIncidentId}
            onClose={() => setActiveChatIncidentId(null)}
          />
        )}

        <ObjectInspector data={selectedObjectData} onClose={() => setActiveObjectId(null)} theme={theme} />
        <VideoModal userId={activeObjectId} onClose={() => setActiveObjectId(null)} theme={theme} />

        <CyberHUD
          activeNode={activeNode}
          setActiveNode={setActiveNode}
          theme={theme}
          activeTab={activeTab}
        />
      </div>
    </DashboardLayout>
  );
}
