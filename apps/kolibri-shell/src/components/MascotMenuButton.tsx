import { Menu } from 'lucide-react';

interface MascotMenuButtonProps {
  open: boolean;
  onToggle(): void;
}

export function MascotMenuButton({ open, onToggle }: MascotMenuButtonProps) {
  return (
    <button
      className={`mascot-menu-button${open ? ' is-open' : ''}`}
      type="button"
      aria-label={open ? 'Закрыть историю' : 'Открыть историю'}
      aria-expanded={open}
      onClick={onToggle}
    >
      <img
        className="mascot-menu-image"
        src="/kolibri-bird.png"
        alt=""
        data-testid="kolibri-mascot"
      />
      <Menu className="mascot-menu-icon" aria-hidden="true" strokeWidth={1.8} />
    </button>
  );
}
