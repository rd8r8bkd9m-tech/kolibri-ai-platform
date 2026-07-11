import { Brand } from "./Brand";

export function SystemBar({ title, subtitle, children, navigationLabel = "Управление рабочим пространством" }) {
  return (
    <header className="system-bar">
      <Brand />
      <div className="workspace-title">
        <strong>{title}</strong>
        <span>{subtitle}</span>
      </div>
      <nav aria-label={navigationLabel}>{children}</nav>
    </header>
  );
}
