import React from 'react';
import Dashboard from './pages/Dashboard';
import useWebSocket from './hooks/useWebSocket';

function App() {
  useWebSocket();

  return (
    <div className="App w-screen h-screen bg-slate-950 text-slate-100 overflow-hidden font-sans antialiased">
      <Dashboard />
    </div>
  );
}

export default App;
