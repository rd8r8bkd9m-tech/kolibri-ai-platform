import { Brand } from "./Brand";

export function SystemBar({ title, subtitle, children, brandLabel, navigationLabel = "Управление рабочим пространством", navigationOpen = false, onBrandActivate, onBrandPreviewEnter, onBrandPreviewLeave }) {
  return (
    <header className="system-bar">
      <Brand expanded={navigationOpen} label={brandLabel} onActivate={onBrandActivate} onPreviewEnter={onBrandPreviewEnter} onPreviewLeave={onBrandPreviewLeave} />
      <div className="workspace-title">
        <strong>{title}</strong>
        <span>{subtitle}</span>
      </div>
      <nav aria-label={navigationLabel}>{children}</nav>
    </header>
  );
}
