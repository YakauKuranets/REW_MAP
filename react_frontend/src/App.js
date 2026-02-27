import React from 'react';
import { BrowserRouter, Route, Routes } from 'react-router-dom';
import Dashboard from './pages/Dashboard';
import MiniTerminal from './components/MiniTerminal';
import useWebSocket from './hooks/useWebSocket';

function App() {
  useWebSocket();

  return (
    <BrowserRouter>
      <div className="App w-screen h-screen bg-slate-950 text-slate-100 overflow-hidden font-sans antialiased">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/webapp" element={<MiniTerminal />} />
          <Route path="*" element={<Dashboard />} />
        </Routes>
      </div>
    </BrowserRouter>
  );
}

export default App;
