export function SettingsPanel({ theme, setTheme, resolvedTheme, pwaStatus }) {
  const options = [
    { id: "system", label: "Системная" },
    { id: "light", label: "Светлая" },
    { id: "dark", label: "Тёмная" },
  ]

  return (
    <div className="control-section">
      <div className="control-section-head">
        <h3>Тема</h3>
        <span className="control-pill">{resolvedTheme === "light" ? "светлая" : "тёмная"}</span>
      </div>
      <div className="theme-segments">
        {options.map(option => (
          <button
            key={option.id}
            className={theme === option.id ? "active" : ""}
            onClick={() => setTheme(option.id)}
            type="button"
          >
            {option.label}
          </button>
        ))}
      </div>
      <div className="pwa-status">
        <div>
          <strong>PWA</strong>
          <span>{pwaStatus}</span>
        </div>
      </div>
    </div>
  )
}
