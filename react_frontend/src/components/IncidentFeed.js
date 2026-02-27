import React, { useEffect, useRef } from 'react';
import useMapStore from '../store/useMapStore'; // Замени на свой стор, если нужно

const IncidentFeed = () => {
    // Получаем инциденты из стора или используем заглушки для демонстрации
    const incidents = useMapStore(state => state.incidents) || [];
    const feedEndRef = useRef(null);

    // Автоскролл вниз при новом сообщении
    useEffect(() => {
        feedEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [incidents]);

    // Функция генерации префикса в зависимости от типа/важности
    const getPrefix = (priority) => {
        switch(priority) {
            case 'CRITICAL': return '[SYS.CRIT]';
            case 'HIGH': return '[WARN]';
            case 'INFO': return '[NET.INFO]';
            default: return '[SYS.OP]';
        }
    };

    const getColorClass = (priority) => {
        switch(priority) {
            case 'CRITICAL': return 'text-red-500 drop-shadow-[0_0_5px_rgba(239,68,68,0.8)]';
            case 'HIGH': return 'text-amber-400 drop-shadow-[0_0_5px_rgba(251,191,36,0.8)]';
            case 'INFO': return 'text-cyan-400 drop-shadow-[0_0_5px_rgba(34,211,238,0.8)]';
            default: return 'text-green-500 drop-shadow-[0_0_5px_rgba(34,197,94,0.8)]';
        }
    };

    return (
        <div className="relative h-64 w-full bg-[#050505] border border-cyan-900/50 rounded flex flex-col font-mono text-sm overflow-hidden shadow-[0_0_15px_rgba(0,240,255,0.1)]">
            {/* Оверлей сканлайнов (эффект старого монитора) */}
            <div className="absolute inset-0 scanlines z-10"></div>
            
            {/* Шапка терминала */}
            <div className="bg-cyan-950/40 border-b border-cyan-900/50 p-1 px-3 flex justify-between items-center z-20">
                <span className="text-cyan-500 font-bold text-xs tracking-widest uppercase">Target.Feed // SEC_NET_v4.0</span>
                <span className="text-cyan-700 text-xs animate-pulse">REC</span>
            </div>

            {/* Лог событий */}
            <div className="flex-1 overflow-y-auto p-3 space-y-2 z-20 scrollbar-thin scrollbar-thumb-cyan-900 scrollbar-track-transparent">
                {incidents.length === 0 ? (
                    <div className="text-green-600/50 cyber-terminal-line">
                        [SYS.OP] Установка защищенного соединения... ОК.
                        <br/>
                        [SYS.OP] Ожидание сигналов телеметрии...
                    </div>
                ) : (
                    incidents.map((inc, index) => (
                        <div key={inc.id || index} className="flex gap-2">
                            <span className="text-gray-500 min-w-[70px]">
                                {new Date(inc.timestamp || Date.now()).toLocaleTimeString('en-US', {hour12:false})}
                            </span>
                            <span className={`${getColorClass(inc.priority)} font-bold`}>
                                {getPrefix(inc.priority)}
                            </span>
                            <span className={`text-gray-300 ${index === incidents.length - 1 ? 'cyber-terminal-line' : ''}`}>
                                {inc.description || inc.message || "Неизвестная активность узла"}
                            </span>
                        </div>
                    ))
                )}
                <div ref={feedEndRef} />
            </div>
        </div>
    );
};

export default IncidentFeed;
