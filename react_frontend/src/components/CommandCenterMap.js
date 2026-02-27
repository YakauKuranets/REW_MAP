import React, { useEffect, useMemo, useState } from 'react';
import DeckGL from '@deck.gl/react';
import { ColumnLayer, IconLayer, PathLayer, ScatterplotLayer, TextLayer } from '@deck.gl/layers';
import { FlyToInterpolator, WebMercatorViewport } from '@deck.gl/core';
import Map, { Marker } from 'react-map-gl/maplibre';
import { Loader2, Lock, Radar, Search } from 'lucide-react';
import 'maplibre-gl/dist/maplibre-gl.css';

import useMapStore from '../store/useMapStore';
import useMapClusters from '../hooks/useMapClusters';
import { initPmtiles } from '../vendor/pmtilesSetup';
import TacticalGridDashboard from './TacticalGridDashboard';
import { useNotify } from './NotificationProvider';

const INITIAL_VIEW_STATE = {
  longitude: 27.56,
  latitude: 53.9,
  zoom: 14,
  pitch: 60,
  bearing: -20,
  maxPitch: 85,
};

const MAP_STYLE = '/map_style_cyberpunk.json';

initPmtiles();

const toNumber = (value) => {
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
};

const isViolationAgent = (agent) => Boolean(
  agent?.isViolation
  || agent?.violation
  || agent?.in_violation
  || agent?.zone_violation
  || agent?.inside_polygon,
);

const svgIcon = (fill, stroke = '#ffffff') => `data:image/svg+xml;utf8,${encodeURIComponent(
  `<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64"><circle cx="32" cy="32" r="20" fill="${fill}" stroke="${stroke}" stroke-width="4" /></svg>`,
)}`;

const ICONS = {
  cluster: { url: svgIcon('#334155', '#e2e8f0'), width: 64, height: 64, anchorY: 32 },
  agent: { url: svgIcon('#19d3ff', '#78ebff'), width: 64, height: 64, anchorY: 32 },
  danger: { url: svgIcon('#ef4444', '#fecaca'), width: 64, height: 64, anchorY: 32 },
  incident: { url: svgIcon('#f59e0b', '#fef3c7'), width: 64, height: 64, anchorY: 32 },
  pending: { url: svgIcon('#fde047', '#fef9c3'), width: 64, height: 64, anchorY: 32 },
  camera: { url: svgIcon('#a78bfa', '#ddd6fe'), width: 64, height: 64, anchorY: 32 },
  unknown: { url: svgIcon('#64748b', '#cbd5e1'), width: 64, height: 64, anchorY: 32 },
};

const toActiveNodePayload = (selected) => {
  if (!selected) return null;
  return {
    id: selected.id ?? selected.camera_id ?? selected.agent_id ?? null,
    ip: selected.ip ?? selected.camera_ip ?? selected.host ?? null,
    name: selected.name ?? selected.title ?? selected.camera_name ?? selected.label ?? null,
    raw: selected,
  };
};

export default function CommandCenterMap({ onUserClick, flyToTarget, filters, setActiveNode }) {
  const effectiveFilters = filters || {
    showAgents: true,
    showCameras: true,
    showIncidents: true,
    showPending: true,
  };
  const agentsMap = useMapStore((s) => s.agents);
  const agentsData = useMapStore((s) => s.getAgentsArray());
  const trackPointsData = useMapStore((s) => s.getTracksArray());
  const threatsData = useMapStore((s) => s.getThreatsArray());
  const incidents = useMapStore((s) => s.incidents);
  const pendingMarkers = useMapStore((s) => s.pendingMarkers);
  const terminals = useMapStore((s) => s.terminals || s.markers || []);
  const setSelectedObject = useMapStore((s) => s.setSelectedObject);
  const draftMarker = useMapStore((s) => s.draftMarker);
  const addMarker = useMapStore((s) => s.addMarker);
  const clearDraftMarker = useMapStore((s) => s.clearDraftMarker);

  const { addNotify } = useNotify();

  const [pulseTick, setPulseTick] = useState(0);
  const [activeTerminalId, setActiveTerminal] = useState(null);
  const [isSavingObject, setIsSavingObject] = useState(false);
  const [isDiscovering, setIsDiscovering] = useState(false);
  const [discoveryResult, setDiscoveryResult] = useState(null);
  const [discoveryError, setDiscoveryError] = useState('');
  const [formValues, setFormValues] = useState({
    title: '',
    address: '',
    description: '',
    image: '',
    host: '',
    login: '',
    password: '',
  });
  const [viewState, setViewState] = useState(INITIAL_VIEW_STATE);
  const [viewportSize, setViewportSize] = useState({ width: window.innerWidth, height: window.innerHeight });

  useEffect(() => {
    if (!draftMarker) return;
    setFormValues({
      title: draftMarker.title || draftMarker.name || '',
      address: draftMarker.address || '',
      description: draftMarker.description || '',
      image: draftMarker.image || '',
      host: draftMarker.ip || draftMarker.host || draftMarker.url || '',
      login: draftMarker.ftp_user || draftMarker.login || '',
      password: draftMarker.ftp_password || draftMarker.password || '',
    });
    setDiscoveryResult(null);
    setDiscoveryError('');
  }, [draftMarker]);

  useEffect(() => {
    const onResize = () => setViewportSize({ width: window.innerWidth, height: window.innerHeight });
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  useEffect(() => {
    let raf = 0;
    let mounted = true;

    const loop = () => {
      if (!mounted) return;
      setPulseTick((x) => (x + 1) % 10_000);
      raf = window.requestAnimationFrame(loop);
    };

    raf = window.requestAnimationFrame(loop);
    return () => {
      mounted = false;
      window.cancelAnimationFrame(raf);
    };
  }, []);

  useEffect(() => {
    if (!flyToTarget) return;
    setViewState((prev) => ({
      ...prev,
      longitude: flyToTarget.lon,
      latitude: flyToTarget.lat,
      zoom: Math.max(prev.zoom, 14.5),
      transitionInterpolator: new FlyToInterpolator({ speed: 1.2 }),
      transitionDuration: 900,
    }));
  }, [flyToTarget]);

  const normalizedAgents = useMemo(
    () => Object.values(agentsMap || {})
      .map((agent) => {
        const lon = toNumber(agent.lon ?? agent.longitude);
        const lat = toNumber(agent.lat ?? agent.latitude);
        if (lon === null || lat === null) return null;
        return {
          ...agent,
          lon,
          lat,
          type: isViolationAgent(agent) ? 'danger' : 'agent',
        };
      })
      .filter(Boolean),
    [agentsMap],
  );



  const normalizedIncidents = useMemo(
    () => (incidents || [])
      .map((incident) => {
        const lon = toNumber(incident.lon ?? incident.longitude);
        const lat = toNumber(incident.lat ?? incident.latitude);
        if (lon === null || lat === null) return null;
        return { ...incident, lon, lat, type: 'incident' };
      })
      .filter(Boolean),
    [incidents],
  );

  const normalizedPending = useMemo(
    () => (pendingMarkers || [])
      .map((pending) => {
        const lon = toNumber(pending.lon ?? pending.longitude);
        const lat = toNumber(pending.lat ?? pending.latitude);
        if (lon === null || lat === null) return null;
        return { ...pending, lon, lat, type: 'pending' };
      })
      .filter(Boolean),
    [pendingMarkers],
  );

  const normalizedTerminals = useMemo(
    () => (terminals || [])
      .map((terminal) => {
        const lon = toNumber(terminal.lon ?? terminal.longitude);
        const lat = toNumber(terminal.lat ?? terminal.latitude);
        if (lon === null || lat === null) return null;
        return {
          ...terminal,
          lon,
          lat,
          type: 'terminal',
          channels: Array.isArray(terminal.channels) ? terminal.channels : [],
        };
      })
      .filter(Boolean),
    [terminals],
  );

  const activeTerminal = useMemo(
    () => normalizedTerminals.find((terminal) => String(terminal.id) === String(activeTerminalId)) || null,
    [normalizedTerminals, activeTerminalId],
  );

  const filteredData = useMemo(() => ([
    ...(effectiveFilters.showAgents ? normalizedAgents : []),
    ...(effectiveFilters.showIncidents ? normalizedIncidents : []),
    ...(effectiveFilters.showPending ? normalizedPending : []),
  ]), [effectiveFilters, normalizedAgents, normalizedIncidents, normalizedPending]);

  const bounds = useMemo(() => {
    try {
      const viewport = new WebMercatorViewport({
        ...viewState,
        width: viewportSize.width,
        height: viewportSize.height,
      });
      return viewport.getBounds();
    } catch (_e) {
      return null;
    }
  }, [viewState, viewportSize]);

  const clusteredData = useMapClusters({
    data: filteredData,
    zoom: viewState.zoom,
    bounds,
  });

  const sosPulse = Math.sin(pulseTick * 0.15) * 0.5 + 0.5;

  const layers = useMemo(() => {
    const neonTracksLayer = new PathLayer({
      id: 'agent-tracks-layer',
      data: trackPointsData,
      pickable: true,
      widthScale: 1,
      widthMinPixels: 2,
      widthMaxPixels: 6,
      getPath: (d) => d.path,
      getColor: () => [0, 240, 255, 220],
      shadowEnabled: true,
      updateTriggers: {
        getPath: [trackPointsData],
      },
    });

    const neonAgentsLayer = new ScatterplotLayer({
      id: 'active-agents-layer',
      data: agentsData,
      pickable: true,
      opacity: 0.9,
      stroked: true,
      filled: true,
      radiusScale: 1,
      radiusMinPixels: 6,
      radiusMaxPixels: 14,
      lineWidthMinPixels: 2,
      getPosition: (d) => d.coordinates,
      getFillColor: () => [255, 0, 60, 255],
      getLineColor: () => [0, 240, 255, 255],
      updateTriggers: {
        getPosition: [agentsData],
      },
      transitions: {
        getPosition: 300,
      },
    });

    const iconLayer = new IconLayer({
      id: 'clustered-icon-layer',
      data: clusteredData,
      pickable: true,
      sizeScale: 1,
      getPosition: (d) => d.geometry.coordinates,
      getIcon: (d) => {
        if (d.properties.cluster) return ICONS.cluster;
        const key = d.properties.entityType;
        return ICONS[key] || ICONS.unknown;
      },
      getSize: (d) => {
        if (d.properties.cluster) {
          const count = d.properties.point_count || 1;
          return Math.min(36 + Math.log2(count) * 10, 76);
        }
        if (d.properties.entityType === 'danger') return 42 + sosPulse * 8;
        return 30;
      },
      sizeUnits: 'pixels',
      transitions: {
        getPosition: 300,
      },
    });


    const threatPillarLayer = new ColumnLayer({
      id: 'threat-pillar-layer',
      data: threatsData,
      diskResolution: 6,
      radius: 15,
      extruded: true,
      pickable: true,
      elevationScale: 1,
      getPosition: (d) => [parseFloat(d.lon), parseFloat(d.lat)],
      getFillColor: () => [255, 176, 0, 180],
      getLineColor: () => [255, 176, 0, 255],
      getElevation: () => 150,
      updateTriggers: {
        getPosition: [threatsData],
        getFillColor: [threatsData],
      },
      transitions: {
        getElevation: {
          duration: 800,
          type: 'spring',
        },
      },
    });

    const clusterLabelLayer = new TextLayer({
      id: 'cluster-count-layer',
      data: clusteredData.filter((d) => d.properties.cluster),
      pickable: false,
      billboard: true,
      getPosition: (d) => d.geometry.coordinates,
      getText: (d) => String(d.properties.point_count || ''),
      getColor: [255, 255, 255, 255],
      getSize: 16,
      getTextAnchor: 'middle',
      getAlignmentBaseline: 'center',
      characterSet: 'auto',
      sizeUnits: 'pixels',
      fontSettings: {
        fontWeight: 800,
      },
    });

    return [neonTracksLayer, neonAgentsLayer, iconLayer, threatPillarLayer, clusterLabelLayer];
  }, [agentsData, clusteredData, sosPulse, trackPointsData, threatsData]);

  const forwardGeocode = async () => {
    const q = (formValues.address || '').trim();
    if (!q) return;
    try {
      const url = `https://nominatim.openstreetmap.org/search?format=json&limit=1&q=${encodeURIComponent(q)}`;
      const response = await fetch(url, { headers: { Accept: 'application/json' } });
      const data = await response.json();
      if (!Array.isArray(data) || !data[0]) return;
      const lat = Number(data[0].lat);
      const lon = Number(data[0].lon);
      if (!Number.isFinite(lat) || !Number.isFinite(lon)) return;
      setViewState((prev) => ({
        ...prev,
        longitude: lon,
        latitude: lat,
        zoom: Math.max(prev.zoom || 0, 15),
        transitionInterpolator: new FlyToInterpolator({ speed: 1.2 }),
        transitionDuration: 1000,
      }));
    } catch (_err) {
      // geocode failures are intentionally non-blocking
    }
  };

  const onImageSelected = (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      const base64 = typeof reader.result === 'string' ? reader.result : '';
      setFormValues((prev) => ({ ...prev, image: base64 }));
    };
    reader.readAsDataURL(file);
  };

  const handleAnalyzeNode = async () => {
    if (!draftMarker || isDiscovering) return;
    setIsDiscovering(true);
    setDiscoveryResult(null);
    setDiscoveryError('');
    try {
      const resp = await fetch('/api/terminals/discover', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ip: formValues.host,
          username: formValues.login,
          password: formValues.password,
        }),
      });
      const data = await resp.json().catch(() => ({}));
      if (resp.ok && data?.status === 'success') {
        setDiscoveryResult(data);
        addNotify(`Успешно: терминал ${data?.type || "UNKNOWN"}, каналов: ${(data?.channels || []).length}`, "success");
      } else {
        setDiscoveryError('❌ Не удалось определить тип устройства. Проверьте IP и пароль');
        addNotify('Не удалось определить тип устройства. Проверьте IP и пароль', "error");
      }
    } catch (_err) {
      setDiscoveryError('❌ Не удалось определить тип устройства. Проверьте IP и пароль');
      addNotify('Ошибка сети при анализе узла', "error");
    } finally {
      setIsDiscovering(false);
    }
  };

  const saveDraftObject = async () => {
    if (!draftMarker || isSavingObject) return;
    setIsSavingObject(true);
    try {
      const channels = Array.isArray(discoveryResult?.channels) ? discoveryResult.channels : [];
      const payload = {
        title: formValues.title,
        name: formValues.title,
        address: formValues.address,
        description: formValues.description,
        image: formValues.image,
        ip: formValues.host,
        lat: draftMarker.lat,
        lon: draftMarker.lon,
        terminal_auth: {
          ftp_user: formValues.login,
          ftp_password: formValues.password,
        },
        channels,
      };

      const resp = await fetch('/api/objects', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const saved = await resp.json();
      addMarker({
        id: saved?.id,
        name: saved?.name || formValues.title,
        title: saved?.name || formValues.title,
        address: saved?.address || formValues.address,
        description: saved?.description || formValues.description,
        image: saved?.image || formValues.image,
        ip: saved?.ip || formValues.host,
        lat: saved?.lat ?? draftMarker.lat,
        lon: saved?.lon ?? draftMarker.lon,
        channels,
      });
      clearDraftMarker();
    } catch (_err) {
      // silent UI fail-safe; keeping form open for retry
    } finally {
      setIsSavingObject(false);
    }
  };

  return (
    <div className="absolute inset-0">
      <DeckGL
        viewState={viewState}
        onViewStateChange={({ viewState: nextViewState }) => setViewState(nextViewState)}
        controller
        layers={layers}
        onClick={(info) => {
          if (info?.srcEvent?.stopPropagation) info.srcEvent.stopPropagation();
          if (!info?.object) return;
          const feature = info.object;
          if (feature?.properties?.cluster) {
            if (setActiveNode) setActiveNode(null);
            setActiveTerminal(null);
            const [lon, lat] = feature.geometry.coordinates;
            setViewState((prev) => ({
              ...prev,
              longitude: lon,
              latitude: lat,
              zoom: Math.min((prev.zoom || 0) + 2, 16),
              transitionInterpolator: new FlyToInterpolator({ speed: 1.3 }),
              transitionDuration: 500,
            }));
            return;
          }

          const selected = feature.properties || feature || null;
          if (setActiveNode) setActiveNode(toActiveNodePayload(selected));
          setSelectedObject(selected);
          if (selected?.agent_id && onUserClick) onUserClick(String(selected.agent_id));
        }}
      >
        <Map
          mapStyle={MAP_STYLE}
          reuseMaps
          dragRotate
        >
          {effectiveFilters.showCameras && normalizedTerminals.map((terminal, idx) => (
            <Marker
              key={terminal.id || `terminal-${idx}`}
              longitude={terminal.lon}
              latitude={terminal.lat}
              anchor="center"
            >
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  setActiveTerminal(terminal.id ?? `terminal-${idx}`);
                  setSelectedObject(terminal);
                  if (setActiveNode) {
                    setActiveNode(toActiveNodePayload({
                      ...terminal,
                      camera_name: terminal.name,
                      camera_ip: terminal.ip,
                    }));
                  }
                }}
                className="group relative"
              >
                <span className="pointer-events-none absolute -top-6 left-1/2 -translate-x-1/2 whitespace-nowrap rounded bg-rose-500/20 px-2 py-0.5 text-[10px] font-mono text-rose-400">
                  {(Array.isArray(terminal.channels) ? terminal.channels.length : 0)} CAMS
                </span>
                <span className="block h-4 w-4 animate-pulse rounded-[2px] border-2 border-rose-400 bg-slate-800 shadow-[0_0_18px_rgba(244,63,94,0.45)] transition group-hover:scale-110" />
              </button>
            </Marker>
          ))}
        </Map>
      </DeckGL>

      {activeTerminal && (
        <TacticalGridDashboard
          terminal={activeTerminal}
          onClose={() => setActiveTerminal(null)}
        />
      )}

      {draftMarker && (
        <div className="pointer-events-auto absolute left-1/2 top-1/2 z-40 w-[480px] -translate-x-1/2 -translate-y-1/2 rounded-2xl border border-cyan-500/30 bg-slate-950/90 p-4 shadow-[0_0_40px_rgba(6,182,212,0.25)] backdrop-blur-md">
          <div className="mb-3 font-mono text-sm uppercase tracking-wide text-cyan-300">Регистрация объекта</div>

          <div className="space-y-4">
            <div className="rounded-lg border border-cyan-500/25 bg-slate-900/50 p-3">
              <div className="mb-2 font-mono text-xs uppercase tracking-wide text-cyan-300">Метаданные</div>
              <div className="space-y-2">
                <input
                  value={formValues.title}
                  onChange={(e) => setFormValues((prev) => ({ ...prev, title: e.target.value }))}
                  placeholder="Название / ID"
                  className="w-full rounded border border-cyan-700/40 bg-slate-900/70 px-3 py-2 text-sm text-slate-100 outline-none focus:border-cyan-400"
                />

                <div className="flex gap-2">
                  <input
                    value={formValues.address}
                    onChange={(e) => setFormValues((prev) => ({ ...prev, address: e.target.value }))}
                    placeholder="Адрес"
                    className="flex-1 rounded border border-cyan-700/40 bg-slate-900/70 px-3 py-2 text-sm text-slate-100 outline-none focus:border-cyan-400"
                  />
                  <button
                    type="button"
                    onClick={forwardGeocode}
                    className="inline-flex items-center justify-center rounded border border-cyan-400/60 bg-cyan-500/10 px-3 text-cyan-200 hover:bg-cyan-500/20"
                    title="Найти адрес"
                  >
                    <Search className="h-4 w-4" />
                  </button>
                </div>

                <textarea
                  value={formValues.description}
                  onChange={(e) => setFormValues((prev) => ({ ...prev, description: e.target.value }))}
                  placeholder="Текстовое описание"
                  rows={3}
                  className="w-full rounded border border-cyan-700/40 bg-slate-900/70 px-3 py-2 text-sm text-slate-100 outline-none focus:border-cyan-400"
                />

                <label className="block rounded border border-cyan-700/40 bg-slate-900/70 px-3 py-2 text-xs text-slate-300">
                  Загрузка фото/кадра
                  <input type="file" accept="image/*" onChange={onImageSelected} className="mt-1 block w-full text-xs text-slate-300" />
                </label>
              </div>
            </div>

            <div className="rounded-lg border border-rose-500/25 bg-rose-950/20 p-3">
              <div className="mb-2 font-mono text-xs uppercase tracking-wide text-rose-300">Подключение</div>
              <div className="space-y-2">
                <input
                  value={formValues.host}
                  onChange={(e) => setFormValues((prev) => ({ ...prev, host: e.target.value }))}
                  placeholder="IP / Домен"
                  className="w-full rounded border border-rose-500/30 bg-slate-900/70 px-3 py-2 text-sm text-slate-100 outline-none focus:border-rose-300"
                />
                <div className="grid grid-cols-2 gap-2">
                  <div className="relative">
                    <Lock className="pointer-events-none absolute left-2 top-2.5 h-4 w-4 text-rose-400" />
                    <input
                      value={formValues.login}
                      onChange={(e) => setFormValues((prev) => ({ ...prev, login: e.target.value }))}
                      placeholder="Логин"
                      className="w-full rounded border border-rose-500/30 bg-slate-900/70 px-8 py-2 text-sm text-slate-100 outline-none focus:border-rose-300"
                    />
                  </div>
                  <div className="relative">
                    <Lock className="pointer-events-none absolute left-2 top-2.5 h-4 w-4 text-rose-400" />
                    <input
                      type="password"
                      value={formValues.password}
                      onChange={(e) => setFormValues((prev) => ({ ...prev, password: e.target.value }))}
                      placeholder="Пароль"
                      className="w-full rounded border border-rose-500/30 bg-slate-900/70 px-8 py-2 text-sm text-slate-100 outline-none focus:border-rose-300"
                    />
                  </div>
                </div>
              </div>
            </div>

            <div className="rounded-lg border border-fuchsia-500/25 bg-fuchsia-950/20 p-3">
              <div className="mb-2 font-mono text-xs uppercase tracking-wide text-fuchsia-300">Сканирование</div>
              <button
                type="button"
                onClick={handleAnalyzeNode}
                disabled={isDiscovering || !formValues.host || !formValues.login || !formValues.password}
                className="flex w-full items-center justify-center gap-2 rounded border border-fuchsia-400/60 bg-fuchsia-500/10 px-3 py-2 font-mono text-xs uppercase tracking-wide text-fuchsia-200 transition hover:bg-fuchsia-500/20 disabled:opacity-50"
              >
                {isDiscovering ? <Loader2 className="h-4 w-4 animate-spin" /> : <Radar className="h-4 w-4" />}
                {isDiscovering ? 'Сканирование...' : '[ АНАЛИЗ УЗЛА ]'}
              </button>
            </div>

            {(discoveryResult || discoveryError) && (
              <div className={`rounded border p-2 text-xs font-mono ${discoveryResult ? 'border-emerald-500/30 bg-emerald-900/20 text-emerald-300' : 'border-red-500/30 bg-red-950/20 text-red-300'}`}>
                {discoveryResult
                  ? `✅ Терминал ${discoveryResult?.type || 'UNKNOWN'} готов. Найдено каналов: ${(discoveryResult?.channels || []).length}`
                  : discoveryError}
              </div>
            )}

            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={clearDraftMarker}
                className="rounded border border-slate-600 px-3 py-2 text-xs uppercase tracking-wide text-slate-300 hover:border-slate-400"
              >
                Отмена
              </button>
              <button
                type="button"
                onClick={saveDraftObject}
                disabled={isSavingObject}
                className="rounded border border-cyan-400/60 bg-cyan-500/10 px-3 py-2 text-xs uppercase tracking-wide text-cyan-200 hover:bg-cyan-500/20 disabled:opacity-50"
              >
                {isSavingObject ? 'Сохранение...' : '[ СОХРАНИТЬ ОБЪЕКТ ]'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
