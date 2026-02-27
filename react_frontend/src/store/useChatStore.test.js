import useChatStore from './useChatStore';

describe('useChatStore', () => {
  beforeEach(() => {
    useChatStore.getState().reset();
  });

  test('sets and appends messages per incident immutably', () => {
    const state = useChatStore.getState();

    state.setMessages(101, [{ id: 'm-1', text: 'Начали обработку' }]);
    state.addMessage(101, { id: 'm-2', text: 'Группа выехала' });
    state.addMessage('202', { id: 'm-3', text: 'Другой инцидент' });

    expect(useChatStore.getState().messagesByIncident['101']).toEqual([
      expect.objectContaining({ id: 'm-1' }),
      expect.objectContaining({ id: 'm-2' }),
    ]);

    expect(useChatStore.getState().messagesByIncident['202']).toEqual([
      expect.objectContaining({ id: 'm-3' }),
    ]);
  });
});
