import { useRef, useState } from "react";
import { createPortal } from "react-dom";
import { ChevronRight, FolderKanban, Plus, Trash2 } from "lucide-react";
import { useDialogFocus } from "../app/useDialogFocus";

function DeleteProjectDialog({ busy = false, project, onCancel, onConfirm }) {
  const dialog = useRef(null);
  useDialogFocus(dialog, {
    onEscape: onCancel,
    fallbackFocus: "[data-project-history-focus]",
  });
  const dialogNode = (
    <div className="project-delete-layer">
      <button aria-label="Отменить удаление" className="project-delete-scrim" onClick={onCancel} type="button" />
      <section
        aria-describedby="project-delete-description"
        aria-labelledby="project-delete-title"
        aria-modal="true"
        className="project-delete-dialog"
        ref={dialog}
        role="alertdialog"
        tabIndex={-1}
      >
        <span>Удаление проекта</span>
        <h2 id="project-delete-title">Удалить «{project.title}»?</h2>
        <p id="project-delete-description">Проект исчезнет из истории, а связанные окна закроются. Сразу после удаления действие можно отменить.</p>
        <div>
          <button data-dialog-initial-focus onClick={onCancel} type="button">Отмена</button>
          <button className="danger-action" disabled={busy} onClick={onConfirm} type="button"><Trash2 size={16} /> {busy ? "Проект выполняется" : "Удалить"}</button>
        </div>
      </section>
    </div>
  );
  return globalThis.document?.body ? createPortal(dialogNode, globalThis.document.body) : dialogNode;
}

export function ProjectsWindow({ busyProjects = {}, items, onDelete, onNew, onOpen }) {
  const [confirmProject, setConfirmProject] = useState(null);
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
      <header><span>История проектов</span><button data-project-history-focus onClick={onNew} type="button"><Plus size={16} /> Новый проект</button></header>
      <div className="system-list">{items.map((item) => (
        <article className="project-history-row" key={item.id}>
          <button className="project-history-open" onClick={() => onOpen(item)} type="button">
            <span className="system-list-icon"><FolderKanban size={19} /></span>
            <span>
              <strong>{item.title}</strong>
              <small>{new Date(item.updatedAt || item.createdAt).toLocaleString("ru-RU")} · {item.messages?.length || 0} сообщений</small>
            </span>
            <ChevronRight size={17} />
          </button>
          {onDelete && (
            <button aria-label={busyProjects[item.id] ? `Проект «${item.title}» выполняется и пока не может быть удалён` : `Удалить проект «${item.title}»`} className="project-history-delete" disabled={Boolean(busyProjects[item.id])} onClick={() => setConfirmProject(item)} type="button">
              <Trash2 size={17} />
            </button>
          )}
        </article>
      ))}</div>
      {confirmProject && (
        <DeleteProjectDialog
          busy={Boolean(busyProjects[confirmProject.id])}
          onCancel={() => setConfirmProject(null)}
          onConfirm={() => {
            const projectId = confirmProject.id;
            setConfirmProject(null);
            onDelete(projectId);
          }}
          project={confirmProject}
        />
      )}
    </div>
  );
}
