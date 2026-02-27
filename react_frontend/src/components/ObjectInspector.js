import React from 'react';
import { motion } from 'framer-motion';
import { Activity, Battery, Radio, Navigation2, X, Shield } from 'lucide-react';

export default function ObjectInspector({ data, onClose, theme = 'dark' }) {
  if (!data) return null;

  const isDark = theme === 'dark';

  // Динамические стили для главной панели
  const panelBg = isDark
    ? 'bg-slate-900/60 border-blue-500/20 shadow-[0_0_50px_rgba(30,58,138,0.3)]'
    : 'bg-white/80 border-blue-200 shadow-2xl shadow-blue-900/10';

  const titleColor = isDark ? 'text-slate-100' : 'text-slate-800';
  const subtitleColor = isDark ? 'text-slate-500' : 'text-slate-500';
  const closeBtn = isDark ? 'hover:bg-slate-800/50 text-slate-500 hover:text-white' : 'hover:bg-slate-100 text-slate-400 hover:text-slate-800';

  // Стили для блока координат
  const coordBg = isDark ? 'bg-black/20 border-slate-800/50' : 'bg-slate-50/80 border-slate-200';
  const coordText = isDark ? 'text-blue-300/80' : 'text-blue-600 font-semibold';

  // Стили для кнопки
  const actionBtn = isDark
    ? 'bg-blue-600/20 hover:bg-blue-600/30 border-blue-500/30 text-blue-400'
    : 'bg-blue-50 hover:bg-blue-100 border-blue-200 text-blue-700';

  return (
    <motion.div
      initial={{ x: -400, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      exit={{ x: -400, opacity: 0 }}
      className={`absolute top-24 left-24 w-80 backdrop-blur-xl border rounded-3xl p-6 z-30 transition-colors duration-500 ${panelBg}`}
    >
      {/* Заголовок карточки */}
      <div className="flex justify-between items-start mb-6">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Shield className={`w-4 h-4 ${isDark ? 'text-blue-400' : 'text-blue-600'}`} />
            <h3 className={`text-xl font-bold transition-colors ${titleColor}`}>{data.id}</h3>
          </div>
          <span className={`text-[10px] uppercase tracking-[0.2em] font-bold transition-colors ${subtitleColor}`}>
            Nexus Telemetry v4
          </span>
        </div>
        <button
          onClick={onClose}
          className={`p-2 rounded-full transition-colors ${closeBtn}`}
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Основные показатели (Grid) */}
      <div className="grid grid-cols-2 gap-3">
        <StatBox theme={theme} icon={<Activity className="text-rose-400" />} label="Пульс" value={data.hr || "78 bpm"} sub="Норма" />
        <StatBox theme={theme} icon={<Battery className="text-emerald-400" />} label="Заряд" value={data.battery || "84%"} sub="6ч работы" />
        <StatBox theme={theme} icon={<Navigation2 className="text-sky-400" />} label="Скорость" value={data.speed || "5.2 км/ч"} sub="Пешком" />
        <StatBox theme={theme} icon={<Radio className="text-amber-400" />} label="Mesh-сеть" value={data.meshNodes || "3 узла"} sub="Стабильно" />
      </div>

      {/* Координаты и статус */}
      <div className={`mt-6 p-4 rounded-2xl border transition-colors ${coordBg}`}>
        <div className={`text-[10px] uppercase mb-2 tracking-widest ${subtitleColor}`}>Геопозиция</div>
        <div className={`font-mono text-xs ${coordText}`}>
            {data.lat.toFixed(6)}° N<br/>
            {data.lon.toFixed(6)}° E
        </div>
      </div>

      {/* Кнопка быстрого действия */}
      <button className={`w-full mt-6 py-3 rounded-xl text-xs font-bold uppercase tracking-widest transition-all border ${actionBtn}`}>
        Запросить статус-рапорт
      </button>
    </motion.div>
  );
}

// Прокидываем theme и сюда, чтобы менять цвета плиток
function StatBox({ icon, label, value, sub, theme }) {
  const isDark = theme === 'dark';
  const boxBg = isDark ? 'bg-slate-800/30 border-slate-700/20' : 'bg-white/60 border-slate-200/60 shadow-sm';
  const valColor = isDark ? 'text-slate-100' : 'text-slate-800';
  const labelColor = isDark ? 'text-slate-500' : 'text-slate-500';
  const subColor = isDark ? 'text-slate-400' : 'text-slate-400';

  return (
    <div className={`p-3 rounded-2xl border transition-colors ${boxBg}`}>
      <div className="w-5 h-5 mb-1">{icon}</div>
      <div className={`text-[9px] uppercase font-bold ${labelColor}`}>{label}</div>
      <div className={`text-sm font-bold ${valColor}`}>{value}</div>
      <div className={`text-[8px] ${subColor}`}>{sub}</div>
    </div>
  );
}