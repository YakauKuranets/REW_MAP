import React, { useState } from 'react';

const CTIConsole = () => {
  const [target, setTarget] = useState('');
  const [taskType, setTaskType] = useState('WEB_DIR_ENUM');
  const [context, setContext] = useState('');
  const [status, setStatus] = useState('IDLE');
  const [statusMsg, setStatusMsg] = useState('');

  const handleRun = async () => {
    if (!target) return;
    setStatus('PROCESSING');

    try {
      const res = await fetch('/api/diagnostics/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          target,
          task_type: taskType,
          use_anonymizer: true,
          context: context || null,
        }),
      });

      const data = await res.json();

      if (res.ok && data.status !== 'error') {
        setStatus('SUCCESS');
        setStatusMsg(data.message);
        setTimeout(() => {
          setStatus('IDLE');
          setStatusMsg('');
        }, 4000);
      } else {
        setStatus('ERROR');
        setStatusMsg(data.message || 'Ошибка выполнения задачи');
        setTimeout(() => {
          setStatus('IDLE');
          setStatusMsg('');
        }, 3000);
      }
    } catch (_e) {
      setStatus('ERROR');
      setStatusMsg('Сбой соединения');
    }
  };

  return (
    <div className="mt-3 w-full rounded bg-[#0a0a0a] border border-cyan-800/50 p-4 shadow-lg font-mono text-sm">
      <div className="flex justify-between items-center border-b border-cyan-800/30 pb-2 mb-4">
        <h2 className="text-cyan-400 font-bold tracking-wider flex items-center gap-2">
          <span className="w-2 h-2 bg-cyan-400 animate-pulse" />
          CTI TOOLKIT // DIAGNOSTIC CONSOLE
        </h2>
        <span className={status === 'SUCCESS' ? 'text-green-400 animate-pulse' : status === 'ERROR' ? 'text-red-500' : 'text-gray-500'}>
          STATUS: {status}
        </span>
      </div>

      <div className="space-y-4">
        <div>
          <label className="text-gray-400 block mb-1 text-xs">TARGET (IP / DOMAIN):</label>
          <input
            type="text"
            value={target}
            onChange={(e) => setTarget(e.target.value)}
            placeholder="example.com or 192.168.1.100"
            className="w-full bg-gray-900 border border-cyan-800/50 text-cyan-300 p-2 outline-none focus:border-cyan-400 transition-colors text-sm"
          />
        </div>

        <div>
          <label className="text-gray-400 block mb-1 text-xs">DIAGNOSTIC TASK:</label>
          <select
            value={taskType}
            onChange={(e) => {
              setTaskType(e.target.value);
              setContext('');
            }}
            className="w-full bg-gray-900 border border-cyan-800/50 text-yellow-400 p-2 outline-none text-sm"
          >
            <option value="WEB_DIR_ENUM">Web directory enumeration</option>
            <option value="PORT_SCAN">Network port scan</option>
            <option value="OSINT_RECON">OSINT deep reconnaissance</option>
            <option value="PHISHING_SIMULATION">Phishing simulation</option>
            <option value="AI_TEST_GEN">AI test scenario generation (CVE-based)</option>
          </select>
        </div>

        {(taskType === 'PHISHING_SIMULATION' || taskType === 'AI_TEST_GEN') && (
          <div className="animate-fade-in">
            <label className="text-gray-400 block mb-1 text-xs">
              {taskType === 'PHISHING_SIMULATION' ? 'TEST EMAIL:' : 'CVE ID:'}
            </label>
            <input
              type="text"
              value={context}
              onChange={(e) => setContext(e.target.value)}
              placeholder={taskType === 'PHISHING_SIMULATION' ? 'security@company.com' : 'CVE-2021-44228'}
              className="w-full bg-gray-900 border border-yellow-600/50 text-yellow-300 p-2 outline-none focus:border-yellow-400 text-sm"
            />
          </div>
        )}

        <div className="pt-2">
          <button
            onClick={handleRun}
            disabled={!target}
            className="w-full relative bg-cyan-900/30 border border-cyan-600 text-cyan-300 font-bold py-3 uppercase tracking-wider hover:bg-cyan-800 hover:text-white transition-all active:scale-[0.98] disabled:opacity-50"
          >
            Run Diagnostic Task
          </button>
          {statusMsg && (
            <p className="text-cyan-400 mt-2 text-center font-bold text-xs break-words">
              {statusMsg}
            </p>
          )}
        </div>
        <p className="text-[9px] text-gray-600 text-center">
          [AUTHORISED USE ONLY] All operations require explicit permission from the target owner.
        </p>
      </div>
    </div>
  );
};

export default CTIConsole;
