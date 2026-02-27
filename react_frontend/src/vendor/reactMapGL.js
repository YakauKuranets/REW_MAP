import React from 'react';

export default function Map({ children }) {
  return <div className="h-full w-full bg-slate-900">{children}</div>;
}

export function NavigationControl() {
  return null;
}
