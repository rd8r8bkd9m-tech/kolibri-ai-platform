
export function Bird({ size='md' }) {
  return <div className={`bird bird-${size}`} aria-label="Vista bird">
    <svg viewBox="0 0 128 128" role="img"><defs><linearGradient id="g" x1="12" x2="112" y1="10" y2="116"><stop stopColor="#0f172a"/><stop offset=".46" stopColor="#353a4d"/><stop offset="1" stopColor="#0b0d12"/></linearGradient><radialGradient id="glow" cx="50%" cy="40%" r="60%"><stop stopColor="#fff" stopOpacity=".96"/><stop offset="1" stopColor="#fff" stopOpacity=".16"/></radialGradient></defs><path d="M64 16c23 0 42 16 42 36 0 15-10 28-25 34-10 14-27 24-50 30 5-12 8-23 7-32-12-7-20-19-20-32 0-20 21-36 46-36Z" fill="url(#g)"/><path d="M40 61c14 8 29 8 46 0-6 12-16 19-30 19-10 0-18-3-24-10 2-4 4-7 8-9Z" fill="url(#glow)"/><circle cx="79" cy="48" r="6" fill="#f8fafc"/><circle cx="80" cy="49" r="2.4" fill="#020617"/><path d="M96 42c8-4 15-4 20-1-7 4-12 10-16 18-.3-6-1.7-11-4-17Z" fill="#111827"/></svg>
  </div>;
}
