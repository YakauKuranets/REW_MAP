import useMapStore from './useMapStore';

describe('useMapStore', () => {
  beforeEach(() => {
    useMapStore.getState().reset();
  });

  test('updates agents, incidents, pending markers and chat messages', () => {
    const state = useMapStore.getState();

    state.updateAgent({ agent_id: 'a-1', lat: 53.9, lon: 27.56 });
    state.updateAgent({ agent_id: 'a-1', status: 'on_site' });
    state.addIncident({ id: 1, lat: 53.9, lon: 27.56, category: 'security' });
    state.addIncident({ id: 2, lat: 53.91, lon: 27.57, category: 'fire' });
    state.upsertPendingMarker({ id: 1001, lat: 53.92, lon: 27.58, status: 'pending' });

    expect(useMapStore.getState().agents['a-1']).toEqual(
      expect.objectContaining({ lat: 53.9, lon: 27.56, status: 'on_site' }),
    );
    expect(useMapStore.getState().incidents).toHaveLength(2);
    expect(useMapStore.getState().pendingMarkers).toEqual([
      expect.objectContaining({ id: 1001, status: 'pending' }),
    ]);

    useMapStore.getState().removeIncident(1);
    useMapStore.getState().removePendingMarker(1001);
    expect(useMapStore.getState().incidents).toEqual([
      expect.objectContaining({ id: 2 }),
    ]);
    expect(useMapStore.getState().pendingMarkers).toEqual([]);

    state.addChatMessage({ id: 'm-1', text: 'Принято, выдвигаюсь', sender: 'agent' });
    expect(useMapStore.getState().chatMessages).toEqual([
      expect.objectContaining({ id: 'm-1', sender: 'agent' }),
    ]);
  });

  test('normalizes violation flag in agent payload', () => {
    const state = useMapStore.getState();

    state.updateAgent({ agent_id: 'a-2', lat: 53.91, lon: 27.57, inside_polygon: true });
    expect(useMapStore.getState().agents['a-2']).toEqual(
      expect.objectContaining({ inside_polygon: true, isViolation: true }),
    );

    state.updateAgent({ agent_id: 'a-2', inside_polygon: false });
    expect(useMapStore.getState().agents['a-2']).toEqual(
      expect.objectContaining({ inside_polygon: false, isViolation: false }),
    );
  });
});


test('updates agent location and keeps tail up to 50 points', () => {
  const state = useMapStore.getState();

  for (let i = 0; i < 55; i += 1) {
    state.updateAgentLocation({ agent_id: 'hf-1', lat: 53.9 + i * 0.0001, lon: 27.56 + i * 0.0001 });
  }

  const current = useMapStore.getState();
  expect(current.agents['hf-1']).toEqual(expect.objectContaining({ agent_id: 'hf-1' }));
  expect(current.agents['hf-1'].coordinates).toEqual([27.5654, 53.9054]);
  expect(current.trackPoints['hf-1'].path).toHaveLength(50);
  expect(current.getAgentsArray()).toHaveLength(1);
  expect(current.getTracksArray()).toHaveLength(1);
});
