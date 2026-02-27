import React from 'react';

function ToggleRow({ label, checked, onChange }) {
  return (
    <label className="flex cursor-pointer items-center justify-between rounded-lg border border-gray-700/80 bg-gray-800/50 px-3 py-2">
      <span className="text-sm text-gray-100">{label}</span>
      <button
        type="button"
        aria-pressed={checked}
        onClick={onChange}
        className={`relative h-6 w-11 rounded-full transition-colors ${checked ? 'bg-cyan-500' : 'bg-gray-600'}`}
      >
        <span
          className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform ${checked ? 'translate-x-5' : 'translate-x-0.5'}`}
        />
      </button>
    </label>
  );
}

export default function SmartFilterPanel({ filters, onFiltersChange }) {
  const toggleFilter = (key) => {
    onFiltersChange({ ...filters, [key]: !filters[key] });
  };

  return (
    <div className="absolute right-4 top-4 z-50 w-64 rounded-xl border border-gray-700 bg-gray-900/90 p-4 backdrop-blur">
      <h3 className="mb-3 text-xs font-bold uppercase tracking-[0.18em] text-cyan-300">Smart Filters</h3>
      <div className="space-y-2">
        <ToggleRow label="Показать агентов" checked={filters.showAgents} onChange={() => toggleFilter('showAgents')} />
        <ToggleRow label="Показать камеры" checked={filters.showCameras} onChange={() => toggleFilter('showCameras')} />
        <ToggleRow label="Показать инциденты" checked={filters.showIncidents} onChange={() => toggleFilter('showIncidents')} />
        <ToggleRow label="Показать заявки TWA" checked={filters.showPending} onChange={() => toggleFilter('showPending')} />
      </div>
    </div>
  );
}
