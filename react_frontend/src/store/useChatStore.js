import { create } from '../vendor/zustand';

const initialState = {
  messagesByIncident: {},
};

const useChatStore = create((set) => ({
  ...initialState,

  addMessage: (incidentId, message) => set((state) => {
    if (incidentId === undefined || incidentId === null || !message) return state;

    const normalizedIncidentId = String(incidentId);
    const currentMessages = state.messagesByIncident[normalizedIncidentId] || [];

    return {
      messagesByIncident: {
        ...state.messagesByIncident,
        [normalizedIncidentId]: [...currentMessages, message],
      },
    };
  }),

  setMessages: (incidentId, messages) => set((state) => {
    if (incidentId === undefined || incidentId === null) return state;

    const normalizedIncidentId = String(incidentId);

    return {
      messagesByIncident: {
        ...state.messagesByIncident,
        [normalizedIncidentId]: Array.isArray(messages) ? [...messages] : [],
      },
    };
  }),

  reset: () => set({ ...initialState }),
}));

export default useChatStore;
