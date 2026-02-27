import React, { createContext, useContext, useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Bell, ShieldAlert, CheckCircle, Info } from 'lucide-react';

const NotificationContext = createContext();

export const NotificationProvider = ({ children }) => {
    const [notifications, setNotifications] = useState([]);

    const addNotify = useCallback((msg, type = 'info') => {
        const id = Date.now();
        setNotifications(prev => [...prev, { id, msg, type }]);
        setTimeout(() => {
            setNotifications(prev => prev.filter(n => n.id !== id));
        }, 5000);
    }, []);

    return (
        <NotificationContext.Provider value={{ addNotify }}>
            {children}
            <div className="fixed top-20 left-1/2 -translate-x-1/2 z-[100] flex flex-col gap-2 w-full max-w-md px-4">
                <AnimatePresence>
                    {notifications.map(n => (
                        <motion.div
                            key={n.id}
                            initial={{ opacity: 0, y: -20, scale: 0.9 }}
                            animate={{ opacity: 1, y: 0, scale: 1 }}
                            exit={{ opacity: 0, scale: 0.9 }}
                            className={`p-4 rounded-xl backdrop-blur-md border shadow-2xl flex items-center gap-3 ${
                                n.type === 'error' ? 'bg-red-500/20 border-red-500/50 text-red-200' :
                                n.type === 'success' ? 'bg-emerald-500/20 border-emerald-500/50 text-emerald-200' :
                                'bg-blue-500/20 border-blue-500/50 text-blue-200'
                            }`}
                        >
                            {n.type === 'error' ? <ShieldAlert className="w-5 h-5" /> :
                             n.type === 'success' ? <CheckCircle className="w-5 h-5" /> : <Info className="w-5 h-5" />}
                            <span className="text-sm font-medium">{n.msg}</span>
                        </motion.div>
                    ))}
                </AnimatePresence>
            </div>
        </NotificationContext.Provider>
    );
};

export const useNotify = () => useContext(NotificationContext);