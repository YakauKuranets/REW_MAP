import React, { useEffect, useRef, useState } from 'react';
import ForceGraph2D from 'react-force-graph-2d';

export default function IdentityGraphPanel({ actorData }) {
  const graphRef = useRef();
  const [graphData, setGraphData] = useState({ nodes: [], links: [] });

  useEffect(() => {
    if (actorData && actorData.connections) {
      const nodes = [{ id: actorData.alias, group: 1, val: 20, color: '#FF003C' }];
      const links = [];

      actorData.connections.forEach((conn) => {
        let nodeColor = '#00F0FF';
        if (conn.type === 'CRYPTO_WALLET') nodeColor = '#FFAA00';
        if (conn.type === 'TIMEZONE') nodeColor = '#AA00FF';

        nodes.push({ id: conn.entity, group: 2, val: 10, color: nodeColor });
        links.push({ source: actorData.alias, target: conn.entity, label: conn.relation });
      });

      setGraphData({ nodes, links });
    }
  }, [actorData]);

  return (
    <div className="absolute right-4 top-20 z-50 flex h-96 w-96 flex-col overflow-hidden rounded-lg border border-cyan-900/50 bg-black/80 shadow-[0_0_30px_rgba(0,240,255,0.1)] backdrop-blur-md">
      <div className="flex items-center justify-between border-b border-cyan-900/50 bg-gradient-to-r from-cyan-900/40 to-transparent p-2">
        <span className="font-mono text-[10px] tracking-widest text-cyan-500">OSINT_KRAKEN // IDENTITY_GRAPH</span>
        <span className="animate-pulse text-[10px] text-red-500">LIVE_TRACKING</span>
      </div>

      <div className="relative flex-grow bg-[#020202]">
        {graphData.nodes.length > 0 ? (
          <ForceGraph2D
            ref={graphRef}
            graphData={graphData}
            width={382}
            height={340}
            nodeColor={(node) => node.color}
            nodeRelSize={6}
            linkColor={() => 'rgba(0, 240, 255, 0.4)'}
            linkDirectionalParticles={2}
            linkDirectionalParticleSpeed={0.01}
            backgroundColor="#000000"
            nodeLabel="id"
            onEngineStop={() => graphRef.current.zoomToFit(400, 20)}
          />
        ) : (
          <div className="flex h-full items-center justify-center font-mono text-xs text-cyan-900">AWAITING_INTEL_STREAM...</div>
        )}
      </div>
    </div>
  );
}
