import { ChevronRight, FolderKanban, Plus } from "lucide-react";

export function ProjectsWindow({ items, onNew, onOpen }) {
  if (!items.length) {
    return (
      <div className="system-empty">
        <FolderKanban size={28} />
        <h2>История пока пуста</h2>
        <p>Начните задачу в основном пространстве — Kolibri сохранит проект здесь.</p>
        <button className="system-primary" onClick={onNew} type="button"><Plus size={17} /> Новый проект</button>
      </div>
    );
  }
  return (
    <div className="projects-window">
      <header><span>История проектов</span><button onClick={onNew} type="button"><Plus size={16} /> Новый проект</button></header>
      <div className="system-list">{items.map((item) => (
        <button key={item.id} onClick={() => onOpen(item)} type="button">
          <span className="system-list-icon"><FolderKanban size={19} /></span>
          <span>
            <strong>{item.title}</strong>
            <small>{new Date(item.updatedAt || item.createdAt).toLocaleString("ru-RU")} · {item.messages?.length || 0} сообщений</small>
          </span>
          <ChevronRight size={17} />
        </button>
      ))}</div>
    </div>
  );
}
