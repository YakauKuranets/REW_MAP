import React, { useEffect, useState } from 'react';
import CommandCenterMap from './CommandCenterMap';

export default function MiniTerminal() {
  const [tg, setTg] = useState(null);

  useEffect(() => {
    if (window.Telegram?.WebApp) {
      const webapp = window.Telegram.WebApp;
      webapp.ready();
      webapp.expand();
      if (typeof webapp.enableClosingConfirmation === 'function') {
        webapp.enableClosingConfirmation();
      }
      setTg(webapp);
    }
  }, []);

  return (
    <div
      className="w-full h-screen overflow-hidden relative"
      style={{
        backgroundColor: tg?.themeParams.bg_color || '#000',
        color: tg?.themeParams.text_color || '#fff',
      }}
    >
      <CommandCenterMap isMobile />

      <div className="absolute top-4 left-4 z-10 bg-black/70 p-2 rounded border border-cyan-500/50 backdrop-blur-sm">
        <h1 className="text-cyan-400 font-mono text-sm uppercase tracking-widest">
          {tg?.initDataUnsafe?.user?.username
            ? `AGENT: ${tg.initDataUnsafe.user.username}`
            : 'GHOST PROTOCOL'}
        </h1>
        <div className="text-xs text-gray-400 font-mono mt-1">LIVE TELEMETRY • 5Hz</div>
      </div>

      {tg && (
        <button
          onClick={() => tg.close()}
          className="absolute top-4 right-4 z-10 bg-red-600/80 text-white px-3 py-1 rounded text-sm font-mono"
          type="button"
        >
          ЗАКРЫТЬ
        </button>
      )}
    </div>
  );
}
