type IconProps = { size?: number }

export function HistoryIcon({ size = 20 }: IconProps) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <path d="M4.7 9.2A8 8 0 1 1 4 12" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/>
    <path d="M4.7 4.8v4.4H9" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M12 7.8v4.6l3 1.8" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
}

export function FilesIcon({ size = 20 }: IconProps) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <path d="M7.5 3.5h6l3 3v12A2.5 2.5 0 0 1 14 21H7.5A2.5 2.5 0 0 1 5 18.5V6A2.5 2.5 0 0 1 7.5 3.5Z" stroke="currentColor" strokeWidth="1.7"/>
    <path d="M13.5 3.8v3.4h3.2M8.5 11h5M8.5 14.5h5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
}
