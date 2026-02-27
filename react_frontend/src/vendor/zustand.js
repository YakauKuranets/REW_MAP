import { useSyncExternalStore } from 'react';

export function create(initState) {
  let state;
  const listeners = new Set();

  const setState = (partial) => {
    const next = typeof partial === 'function' ? partial(state) : partial;
    state = { ...state, ...next };
    listeners.forEach((listener) => listener());
  };

  const getState = () => state;

  const api = {
    setState,
    getState,
    subscribe: (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
  };

  state = initState(setState, getState, api);

  function useStore(selector = (s) => s) {
    return useSyncExternalStore(api.subscribe, () => selector(api.getState()));
  }

  useStore.getState = api.getState;
  useStore.setState = api.setState;
  useStore.subscribe = api.subscribe;

  return useStore;
}
