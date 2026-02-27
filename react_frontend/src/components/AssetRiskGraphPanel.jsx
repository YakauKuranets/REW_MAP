import React, { useMemo } from 'react';
import ForceGraph2D from 'react-force-graph-2d';

export default function AssetRiskGraphPanel({ riskData }) {
  const graphData = useMemo(() => {
    const nodes = (riskData?.nodes || []).map((node) => {
      // Определение цвета узла по уровню риска (risk_score от 0 до 1)
      let nodeColor = '#00F0FF'; // базовый (низкий риск)
      if (node.risk_score > 0.3) nodeColor = '#FFAA00'; // средний
      if (node.risk_score > 0.7) nodeColor = '#FF003C'; // высокий
      if (node.risk_score > 0.9) nodeColor = '#FF0000'; // критический

      return {
        id: node.id,
        type: node.type,
        val: 10 + Math.round((node.risk_score || 0) * 15),
        color: nodeColor,
        risk_score: node.risk_score ?? 0,
      };
    });

    const links = (riskData?.edges || []).map((edge) => ({
      source: edge.source,
      target: edge.target,
      label: edge.risk_type,
      weight: edge.weight,
    }));

    return { nodes, links };
  }, [riskData]);

  return (
    <div className="h-80 w-full overflow-hidden rounded-lg border border-cyan-900/40 bg-black/70">
      {graphData.nodes.length > 0 ? (
        <ForceGraph2D
          graphData={graphData}
          width={760}
          height={300}
          nodeColor={(node) => node.color}
          nodeLabel={(node) => `${node.id} (${node.type}) risk=${(node.risk_score || 0).toFixed(2)}`}
          linkColor={() => 'rgba(0, 240, 255, 0.3)'}
          backgroundColor="#000000"
        />
      ) : (
        <div className="flex h-full items-center justify-center font-mono text-xs text-cyan-800">
          NO_RISK_DATA
        </div>
      )}
    </div>
  );
}
