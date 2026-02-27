import React from 'react';
import { act } from 'react-dom/test-utils';
import { createRoot } from 'react-dom/client';
import useMapStore from '../store/useMapStore';
import useChatStore from '../store/useChatStore';
import useWebSocket from './useWebSocket';

function TestHarness({ wsFactory }) {
  useWebSocket({ url: 'ws://test', wsFactory });
  return React.createElement('div', null, 'ok');
}

describe('useWebSocket', () => {
  let container;
  let root;

  beforeEach(() => {
    useMapStore.getState().reset();
    useChatStore.getState().reset();
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
  });

  test('updates Zustand store on telemetry, pending moderation, chat and incident events', () => {
    const socket = {
      onmessage: null,
      close: jest.fn(),
    };
    const wsFactory = jest.fn(() => socket);

    act(() => {
      root.render(React.createElement(TestHarness, { wsFactory }));
    });

    act(() => {
      socket.onmessage({
        data: JSON.stringify({
          event: 'telemetry_update',
          data: { agent_id: 'u-1', lat: 53.95, lon: 27.59, heading: 80 },
        }),
      });

      socket.onmessage({
        data: JSON.stringify({
          event: 'SYS_TELEMETRY',
          data: { cpu_load: 91.2, ram_usage: 67.4, active_nodes: 321, net_traffic: '512 MB/s', hex_dump: 'A1B2C3D4E5F60718293A4B5C' },
        }),
      });

      socket.onmessage({
        data: JSON.stringify({
          event: 'AGENT_LOCATION_UPDATE',
          data: { agent_id: 'u-2', lat: 54.01, lon: 27.51, heading: 101 },
        }),
      });

      socket.onmessage({
        data: JSON.stringify({
          event: 'pending_created',
          data: { id: 101, lat: 53.9, lon: 27.56, category: 'Охрана', status: 'pending' },
        }),
      });

      socket.onmessage({
        data: JSON.stringify({
          event: 'NEW_PENDING_MARKER',
          marker: { id: 102, lat: 53.91, lon: 27.57, status: 'pending' },
        }),
      });

      socket.onmessage({
        data: JSON.stringify({
          event: 'MARKER_APPROVED',
          marker_id: 101,
          new_object: { id: 303, lat: 53.92, lon: 27.58, category: 'approved' },
        }),
      });

      socket.onmessage({
        data: JSON.stringify({
          event: 'MARKER_REJECTED',
          marker_id: 102,
        }),
      });

      socket.onmessage({
        data: JSON.stringify({
          event: 'chat_message',
          data: { id: 'chat-1', text: 'Принял', sender: 'agent' },
        }),
      });

      socket.onmessage({
        data: JSON.stringify({
          event: 'CHAT_MESSAGE',
          incident_id: 9,
          message: { id: 'chat-2', text: 'Подтверждаю', role: 'dispatcher' },
        }),
      });

      socket.onmessage({
        data: JSON.stringify({
          event: 'bridge_event',
          data: {
            event: 'CHAT_MESSAGE',
            incident_id: 77,
            message: { id: 'chat-3', text: 'Nested envelope', role: 'system' },
          },
        }),
      });

      socket.onmessage({
        data: JSON.stringify({
          event: 'new_incident',
          data: { id: 202, lat: 53.91, lon: 27.57, category: 'fire' },
        }),
      });
    });

    const state = useMapStore.getState();
    expect(state.agents['u-1']).toEqual(expect.objectContaining({ lat: 53.95, lon: 27.59, heading: 80 }));
    expect(state.agents['u-2']).toEqual(expect.objectContaining({ lat: 54.01, lon: 27.51, heading: 101 }));
    expect(state.telemetry).toEqual(expect.objectContaining({ cpu_load: 91.2, active_nodes: 321, net_traffic: '512 MB/s' }));
    expect(state.pendingMarkers).toEqual([]);
    expect(state.incidents).toEqual([
      expect.objectContaining({ id: 202, category: 'fire' }),
      expect.objectContaining({ id: 303, category: 'approved' }),
    ]);
    expect(state.chatMessages).toEqual([
      expect.objectContaining({ id: 'chat-1', text: 'Принял', sender: 'agent' }),
      expect.objectContaining({ id: 'chat-2', text: 'Подтверждаю', role: 'dispatcher' }),
    ]);
    expect(useChatStore.getState().messagesByIncident['77']).toEqual([
      expect.objectContaining({ id: 'chat-3', text: 'Nested envelope', role: 'system' }),
    ]);

    act(() => {
      root.unmount();
    });
    expect(socket.close).toHaveBeenCalled();
  });
});
