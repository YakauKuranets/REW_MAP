import React, { useEffect, useRef, useState } from 'react';
import ForceGraph2D from 'react-force-graph-2d';

export default function IdentityGraphPanel({ actorData }) {
  const graphRef = useRef();
  const [showSensitive, setShowSensitive] = useState(false);
  const [graphData, setGraphData] = useState({ nodes: [], links: [] });

  useEffect(() => {
    if (!(actorData && actorData.connections)) return;

    const stringToColor = (str) => {
      let hash = 0;
      for (let i = 0; i < str.length; i += 1) {
        hash = str.charCodeAt(i) + ((hash << 5) - hash);
      }
      let color = '#';
      for (let i = 0; i < 3; i += 1) {
        const value = (hash >> (i * 8)) & 0xFF;
        color += `00${value.toString(16)}`.slice(-2);
      }
      return color;
    };

    const nodes = [{ id: actorData.alias, type: 'THREAT_ACTOR', val: 20, color: '#FF003C' }];
    const links = [];

    actorData.connections.forEach((conn) => {
      let nodeColor = stringToColor(String(conn.entity || 'unknown'));

      if (conn.type === 'THREAT_ACTOR') nodeColor = '#FF0000';
      if (conn.type === 'EMAIL') nodeColor = '#FFA500';
      if (conn.type === 'IP_ADDRESS') nodeColor = '#0000FF';
      if (conn.type === 'DOMAIN') nodeColor = '#800080';
      if (conn.type === 'CAMERA_MODEL') nodeColor = '#E0E0E0';
      if (conn.type === 'GPS_LOCATION') nodeColor = '#FFD700';
      if (conn.type === 'GEO_REGION' && !showSensitive) nodeColor = '#f0f0f0';

      nodes.push({
        id: conn.entity,
        type: conn.type,
        val: conn.type === 'THREAT_ACTOR' ? 18 : 10,
        color: nodeColor,
      });
      links.push({ source: actorData.alias, target: conn.entity, label: conn.relation });
    });

    setGraphData({ nodes, links });
  }, [actorData, showSensitive]);

  return (
    <div className="absolute right-4 top-20 z-50 flex h-[430px] w-96 flex-col overflow-hidden rounded-lg border border-cyan-900/50 bg-black/80 shadow-[0_0_30px_rgba(0,240,255,0.1)] backdrop-blur-md">
      <div className="flex items-center justify-between border-b border-cyan-900/50 bg-gradient-to-r from-cyan-900/40 to-transparent p-2">
        <span className="font-mono text-[10px] tracking-widest text-cyan-500">OSINT_KRAKEN // IDENTITY_GRAPH</span>
        <span className="animate-pulse text-[10px] text-red-500">LIVE_TRACKING</span>
      </div>

      <label className="flex items-center gap-2 border-b border-cyan-900/30 px-2 py-1 font-mono text-[10px] text-cyan-400">
        <input
          type="checkbox"
          checked={showSensitive}
          onChange={(e) => setShowSensitive(e.target.checked)}
        />
        Показать геолокации (конфиденциально)
      </label>

      <div className="relative flex-grow bg-[#020202]">
        {graphData.nodes.length > 0 ? (
          <ForceGraph2D
            ref={graphRef}
            graphData={graphData}
            width={382}
            height={372}
            nodeColor={(node) => node.color}
            nodeRelSize={6}
            linkColor={() => 'rgba(0, 240, 255, 0.4)'}
            linkDirectionalParticles={2}
            linkDirectionalParticleSpeed={0.01}
            backgroundColor="#000000"
            nodeLabel={(node) => `${node.id} (${node.type})`}
            onEngineStop={() => graphRef.current?.zoomToFit(400, 20)}
          />
        ) : (
          <div className="flex h-full items-center justify-center font-mono text-xs text-cyan-900">AWAITING_INTEL_STREAM...</div>
        )}
      </div>
    </div>
  );
}
