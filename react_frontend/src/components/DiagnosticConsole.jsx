import React, { useState } from 'react';

const DiagnosticConsole = () => {
  const [target, setTarget] = useState('');
  const [profile, setProfile] = useState('WEB_DIR_SCAN');
  const [status, setStatus] = useState('IDLE');

  const handleStart = async () => {
    if (!target) return;
    setStatus('PROCESSING');

    try {
      const res = await fetch('/api/audit/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          target,
          scan_profile: profile,
          use_proxy: true,
        }),
      });

      if (res.ok) {
        setStatus('SUCCESS');
        setTimeout(() => setStatus('IDLE'), 3000);
      } else {
        setStatus('ERROR');
      }
    } catch (_e) {
      setStatus('ERROR');
    }
  };

  return (
    <div className="mt-3 w-full rounded border border-cyan-800/50 bg-[#0a0a0a] p-4 font-mono text-sm shadow-lg">
      <div className="mb-4 flex items-center justify-between border-b border-cyan-800/30 pb-2">
        <h2 className="flex items-center gap-2 font-bold tracking-wider text-cyan-400">
          <span className="h-2 w-2 animate-pulse bg-cyan-400" />
          DIAGNOSTIC CONSOLE
        </h2>
        <span className={status === 'SUCCESS' ? 'animate-pulse text-green-400' : 'text-gray-500'}>
          STATUS: {status}
        </span>
      </div>

      <div className="space-y-4">
        <div>
          <label className="mb-1 block text-xs text-gray-400">TARGET (IP / DOMAIN):</label>
          <input
            type="text"
            value={target}
            onChange={(e) => setTarget(e.target.value)}
            placeholder="example.com or 192.168.1.100"
            className="w-full border border-cyan-800/50 bg-gray-900 p-2 text-sm text-cyan-300 outline-none transition-colors focus:border-cyan-400"
          />
        </div>

        <div>
          <label className="mb-1 block text-xs text-gray-400">SCAN PROFILE:</label>
          <select
            value={profile}
            onChange={(e) => setProfile(e.target.value)}
            className="w-full border border-cyan-800/50 bg-gray-900 p-2 text-sm text-yellow-400 outline-none"
          >
            <option value="WEB_DIR_SCAN">Web directory enumeration</option>
            <option value="PORT_SCAN">Network port scan</option>
            <option value="OSINT_DEEP">Deep OSINT reconnaissance</option>
          </select>
        </div>

        <div className="pt-2">
          <button
            onClick={handleStart}
            className="relative w-full border border-cyan-600 bg-cyan-900/30 py-3 font-bold uppercase tracking-wider text-cyan-300 transition-all hover:bg-cyan-800 hover:text-white active:scale-[0.98] disabled:opacity-50"
            disabled={!target}
          >
            Start Diagnostic Scan
          </button>
          <p className="mt-2 text-center text-[10px] text-gray-600">
            [INFO] Traffic will be anonymized via distributed proxies. Use only on authorized systems.
          </p>
        </div>
      </div>
    </div>
  );
};

export default DiagnosticConsole;
