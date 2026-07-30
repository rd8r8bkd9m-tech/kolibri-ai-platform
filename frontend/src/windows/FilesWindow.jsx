import { Check, FileText, Files } from "lucide-react";
import { materializedArtifacts } from "../shell/projectModel";

export function FilesWindow({ items }) {
  const files = materializedArtifacts(items);
  if (!files.length) {
    return (
      <div className="system-empty">
        <Files size={28} />
        <h2>Проверенных файлов пока нет</h2>
        <p>Здесь появляются только реально материализованные артефакты, а не упоминания путей.</p>
      </div>
    );
  }
  return (
    <div className="system-list">
      {files.map((item, index) => (
        <article key={item.reference_sha256 || item.id || `${item.name}-${index}`}>
          <span className="system-list-icon"><FileText size={19} /></span>
          <span>
            <strong>{item.display_name || item.name || item.kind || `Файл ${index + 1}`}</strong>
            <small>{item.media_type || item.deliverable_type || "artifact"} · материализован</small>
          </span>
          <Check size={17} />
        </article>
      ))}
    </div>
  );
}
