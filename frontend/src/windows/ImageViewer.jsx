import { Download } from "lucide-react";
import { imageArtifactUrl } from "../runtime/artifactLocators";

export function ImageViewer({ artifact }) {
  const source = imageArtifactUrl(artifact);
  if (!source) {
    return <div className="inline-error">Проверенное изображение недоступно.</div>;
  }
  return (
    <section className="image-viewer" aria-label="Просмотр изображения">
      <div className="image-viewer-stage">
        <img alt={artifact.name || "Изображение Kolibri"} src={source} />
      </div>
      <footer>
        <span>{artifact.name || "Изображение Kolibri"}</span>
        <a download href={imageArtifactUrl(artifact, { download: true })}><Download size={16} /> Скачать</a>
      </footer>
    </section>
  );
}
