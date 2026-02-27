import React, { useEffect, useRef, useState } from 'react';
import useMapStore from '../store/useMapStore';

const WHEP_OFFER_ENDPOINT = '/api/webrtc/whep/offer';

export default function CyberHUD({ activeNode, setActiveNode, theme, activeTab }) {
  const videoRef = useRef(null);
  const [streamState, setStreamState] = useState('idle');
  const [streamError, setStreamError] = useState('');
  const telemetry = useMapStore((state) => state.telemetry);

  useEffect(() => {
    if (!activeNode || activeTab !== 'radar') return undefined;

    let cancelled = false;
    let localStream = null;
    let peer = null;

    const attachLiveStream = async () => {
      setStreamState('connecting');
      setStreamError('');

      try {
        peer = new RTCPeerConnection({
          iceServers: [{ urls: ['stun:stun.l.google.com:19302'] }],
        });

        peer.ontrack = (event) => {
          if (cancelled || !videoRef.current) return;
          localStream = event.streams?.[0] || new MediaStream([event.track]);
          videoRef.current.srcObject = localStream;
        };

        const offerResp = await fetch(WHEP_OFFER_ENDPOINT, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            node_id: activeNode.id,
            node_ip: activeNode.ip,
            node_name: activeNode.name,
          }),
        });

        if (!offerResp.ok) {
          throw new Error(`WHEP offer failed: ${offerResp.status}`);
        }

        const offerData = await offerResp.json();
        const remoteSdp = offerData?.sdp;
        const remoteType = offerData?.type || 'offer';

        if (!remoteSdp) throw new Error('Backend returned empty SDP offer');

        await peer.setRemoteDescription({ type: remoteType, sdp: remoteSdp });
        const answer = await peer.createAnswer();
        await peer.setLocalDescription(answer);

        const answerUrl = offerData?.answerUrl || offerData?.sessionUrl || WHEP_OFFER_ENDPOINT;
        await fetch(answerUrl, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            type: 'answer',
            sdp: answer.sdp,
            sessionId: offerData?.sessionId,
            node_id: activeNode.id,
          }),
        });

        if (!cancelled) setStreamState('live');
      } catch (err) {
        if (!cancelled) {
          setStreamState('error');
          setStreamError(err instanceof Error ? err.message : 'Unknown stream error');
        }
      }
    };

    attachLiveStream();

    return () => {
      cancelled = true;
      if (videoRef.current) videoRef.current.srcObject = null;
      if (localStream) {
        localStream.getTracks().forEach((track) => track.stop());
      }
      if (peer) peer.close();
      setStreamState('idle');
      setStreamError('');
    };
  }, [activeNode, activeTab]);

  if (activeTab !== 'radar') return null;

  return (
    <>

      <div className="pointer-events-none absolute right-4 top-4 z-50 w-64 border border-[#00F0FF]/30 bg-[#050505]/80 p-4 font-mono shadow-[0_0_15px_rgba(0,240,255,0.1)]">
        <h3 className="mb-3 border-b border-[#00F0FF]/30 pb-1 text-xs font-bold tracking-[0.2em] text-[#00F0FF]">
          SYS.MONITOR // v4.0
        </h3>

        <div className="space-y-2 text-xs">
          <div className="flex justify-between">
            <span className="text-gray-500">CPU.CORE_LOAD</span>
            <span className={telemetry.cpu_load > 85 ? 'animate-pulse text-[#FF003C]' : 'text-[#00FF41]'}>
              {telemetry.cpu_load}%
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500">RAM.ALLOCATED</span>
            <span className="text-[#00FF41]">{telemetry.ram_usage}%</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500">NET.UPLINK</span>
            <span className="text-[#00F0FF]">{telemetry.net_traffic}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500">NODES.ACTIVE</span>
            <span className="text-[#FFB000]">{telemetry.active_nodes}</span>
          </div>

          <div className="mt-4 border-t border-gray-800 pt-2">
            <span className="mb-1 block text-gray-600">MEM.DUMP_STREAM:</span>
            <span className="break-all text-[10px] text-[#00F0FF]/70">{telemetry.hex_dump}</span>
          </div>
        </div>
      </div>

      <div className="pointer-events-none absolute left-1/2 top-1/2 z-10 -translate-x-1/2 -translate-y-1/2 transform opacity-20">
        <div className={`flex h-32 w-32 items-center justify-center rounded-full border transition-colors ${theme === 'dark' ? 'border-slate-500' : 'border-slate-400'}`}>
          <div className={`absolute top-0 h-4 w-1 ${theme === 'dark' ? 'bg-slate-500' : 'bg-slate-400'}`} />
          <div className={`absolute bottom-0 h-4 w-1 ${theme === 'dark' ? 'bg-slate-500' : 'bg-slate-400'}`} />
          <div className={`absolute left-0 h-1 w-4 ${theme === 'dark' ? 'bg-slate-500' : 'bg-slate-400'}`} />
          <div className={`absolute right-0 h-1 w-4 ${theme === 'dark' ? 'bg-slate-500' : 'bg-slate-400'}`} />
          <div className="h-1 w-1 rounded-full bg-red-500" />
        </div>
      </div>

      <div className="pointer-events-none absolute bottom-5 right-5 z-20 rounded border border-cyan-500/30 bg-black/30 px-2 py-1 text-[10px] uppercase tracking-wide text-cyan-200/80">
        Active node: {activeNode?.name || activeNode?.id || 'none'}
      </div>

      {activeNode && (
        <div className="pointer-events-auto absolute right-6 top-1/2 z-30 w-[420px] -translate-y-1/2 rounded-xl bg-slate-900/80 p-4 backdrop-blur-md border-l-4 border-cyan-500 shadow-[0_0_30px_rgba(6,182,212,0.3)]">
          <div className="font-mono text-sm uppercase tracking-wide text-cyan-300">
            [ UPLINK ESTABLISHED: {activeNode?.name || activeNode?.id || 'UNKNOWN NODE'} ]
          </div>

          <div className="relative mt-3 overflow-hidden rounded-lg border border-cyan-500/30 bg-slate-950/70">
            <video autoPlay muted playsInline className="w-full h-auto border border-cyan-900" ref={videoRef} />
            <div className="pointer-events-none absolute inset-x-0 top-0 h-10 bg-cyan-500/20 animate-scan" />

            {streamState !== 'live' && (
              <div className="absolute inset-0 flex items-center justify-center bg-slate-950/50 text-xs uppercase tracking-[0.2em] text-cyan-200/70">
                {streamState === 'error' ? `Link Error: ${streamError}` : 'Establishing secure uplink...'}
              </div>
            )}
          </div>

          <button
            type="button"
            onClick={() => setActiveNode && setActiveNode(null)}
            className="mt-4 font-mono text-xs uppercase tracking-wide text-red-400 transition hover:text-red-500"
          >
            [ X ] Terminate connection
          </button>
        </div>
      )}
    </>
  );
}
