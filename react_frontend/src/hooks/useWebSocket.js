import { useEffect, useRef } from 'react';
import useMapStore from '../store/useMapStore';
import useChatStore from '../store/useChatStore';

const asArray = (value) => (Array.isArray(value) ? value : [value]);

const getPendingId = (payload) => payload?.pending_id ?? payload?.marker_id ?? payload?.id;

/**
 * Realtime subscription hook for map, pending moderation and incident chat streams.
 * @param {{url?: string, wsFactory?: (url: string) => WebSocket}} [options]
 * @returns {void}
 */
export default function useWebSocket({
  url = 'ws://localhost:8765',
  wsFactory,
} = {}) {
  const updateAgent = useMapStore((s) => s.updateAgent);
  const batchUpdateAgentLocations = useMapStore((s) => s.batchUpdateAgentLocations);
  const addIncident = useMapStore((s) => s.addIncident);
  const addChatMessage = useMapStore((s) => s.addChatMessage);
  const upsertPendingMarker = useMapStore((s) => s.upsertPendingMarker);
  const removePendingMarker = useMapStore((s) => s.removePendingMarker);
  const setTelemetry = useMapStore((s) => s.setTelemetry);
  const addThreatAlert = useMapStore((s) => s.addThreatAlert);

  const addIncidentChatMessage = useChatStore((s) => s.addMessage);

  // Буфер для накопления координат
  const locationBuffer = useRef([]);
  const frameId = useRef(null);

  useEffect(() => {
    const socket = wsFactory ? wsFactory(url) : new WebSocket(url);

    socket.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data || '{}');
        const eventName = message?.event;
        const data = message?.data;

        if (!eventName) return;

        // НАКОПЛЕНИЕ ПАКЕТОВ ТЕЛЕМЕТРИИ
        if (eventName === 'AGENT_LOCATION_UPDATE') {
          const items = Array.isArray(data) ? data : [data];
          locationBuffer.current.push(...items);

          if (!frameId.current) {
            frameId.current = requestAnimationFrame(() => {
              if (locationBuffer.current.length > 0) {
                batchUpdateAgentLocations(locationBuffer.current);
                locationBuffer.current = [];
              }
              frameId.current = null;
            });
          }
          return;
        }

        if (eventName === 'telemetry_update' || eventName === 'duty_location_update') {
          updateAgent(data);
          return;
        }

        if (eventName === 'SYS_TELEMETRY') {
          setTelemetry(data);
          return;
        }

        if (eventName === 'THREAT_INTEL_ALERT') {
          addThreatAlert(data);
          return;
        }

        if (eventName === 'pending_created' || eventName === 'NEW_PENDING_MARKER') {
          const pendingPayload = data ?? message?.marker ?? message;
          asArray(pendingPayload).forEach((item) => upsertPendingMarker(item));
          return;
        }

        if (
          eventName === 'pending_approved'
          || eventName === 'pending_rejected'
          || eventName === 'MARKER_APPROVED'
          || eventName === 'MARKER_REJECTED'
        ) {
          const pendingId = getPendingId(data) ?? getPendingId(message);
          if (pendingId !== undefined && pendingId !== null) removePendingMarker(pendingId);

          if (eventName === 'MARKER_APPROVED') {
            const approvedObject = data?.new_object ?? message?.new_object;
            if (approvedObject) addIncident(approvedObject);
          }
          return;
        }

        if (eventName === 'new_incident' || eventName === 'new_address' || eventName === 'incident_created' || eventName === 'NEW_INCIDENT') {
          asArray(data).forEach((item) => addIncident(item));
          return;
        }

        if (data?.event === 'CHAT_MESSAGE') {
          useChatStore.getState().addMessage(data?.incident_id, data?.message);
          return;
        }

        if (eventName === 'chat_message' || eventName === 'CHAT_MESSAGE') {
          const chatPayload = data || message?.message;
          if (chatPayload) {
            addChatMessage(chatPayload);
            if (eventName === 'CHAT_MESSAGE') {
              addIncidentChatMessage(message?.incident_id, chatPayload);
            }
          }
        }
      } catch (_error) {
        // ignore malformed websocket frames
      }
    };

    return () => {
      if (frameId.current) {
        cancelAnimationFrame(frameId.current);
        frameId.current = null;
      }
      locationBuffer.current = [];
      if (socket && typeof socket.close === 'function') socket.close();
    };
  }, [url, wsFactory, updateAgent, batchUpdateAgentLocations, addIncident, addChatMessage, upsertPendingMarker, removePendingMarker, setTelemetry, addIncidentChatMessage, addThreatAlert]);
}
