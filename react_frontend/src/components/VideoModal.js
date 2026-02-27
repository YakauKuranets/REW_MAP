import React, { useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, Camera, Signal, Radio } from 'lucide-react';

export default function VideoModal({ userId, onClose }) {
  const videoRef = useRef(null);

  // Здесь в будущем будет реальное подключение к WebRTC (Фаза 3)
  useEffect(() => {
    if (!userId) return;
    console.log(`[WebRTC] Запрос видеопотока от устройства: ${userId}`);
  }, [userId]);

  if (!userId) return null;

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0, y: 50, scale: 0.9 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, scale: 0.9, y: 20 }}
        className="absolute bottom-6 left-1/2 transform -translate-x-1/2 lg:left-80 lg:translate-x-0 w-80 lg:w-96 bg-slate-900/90 backdrop-blur-xl border border-slate-700 p-1 rounded-2xl shadow-[0_10px_40px_rgba(0,0,0,0.7)] z-50 overflow-hidden"
      >
        {/* Шапка плеера */}
        <div className="flex justify-between items-center p-3 border-b border-slate-800">
          <div className="flex items-center gap-2">
            <Camera className="w-5 h-5 text-blue-400" />
            <span className="font-bold text-slate-200 text-xs tracking-widest uppercase">
              ОБЪЕКТ: {userId}
            </span>
          </div>
          <div className="flex items-center gap-3">
            <Signal className="w-4 h-4 text-green-400 animate-pulse" />
            <button onClick={onClose} className="text-slate-400 hover:text-white transition-colors bg-slate-800 rounded-full p-1">
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Экран трансляции */}
        <div className="relative w-full aspect-video bg-black flex items-center justify-center overflow-hidden rounded-b-xl">
          <video
            ref={videoRef}
            autoPlay
            playsInline
            muted
            className="w-full h-full object-cover"
          />

          {/* HUD: Декоративные рамки как в бинокле/дроне */}
          <div className="absolute inset-0 border-[1px] border-blue-500/20 pointer-events-none m-2 rounded" />
          <div className="absolute top-4 left-4 w-4 h-4 border-t-2 border-l-2 border-blue-500/50" />
          <div className="absolute top-4 right-4 w-4 h-4 border-t-2 border-r-2 border-blue-500/50" />
          <div className="absolute bottom-4 left-4 w-4 h-4 border-b-2 border-l-2 border-blue-500/50" />
          <div className="absolute bottom-4 right-4 w-4 h-4 border-b-2 border-r-2 border-blue-500/50" />

          {/* Эффект помех / сканлайна */}
          <div className="absolute inset-0 bg-[linear-gradient(rgba(255,255,255,0),rgba(255,255,255,0.05),rgba(255,255,255,0))] bg-[length:100%_4px] opacity-20 pointer-events-none mix-blend-overlay"></div>

          {/* Заглушка, пока нет реального видео */}
          <div className="absolute text-cyan-500/70 text-xs font-mono flex flex-col items-center">
            <Radio className="w-8 h-8 mb-2 opacity-50 animate-ping" />
            УСТАНОВКА СОЕДИНЕНИЯ...
          </div>
        </div>
      </motion.div>
    </AnimatePresence>
  );
}