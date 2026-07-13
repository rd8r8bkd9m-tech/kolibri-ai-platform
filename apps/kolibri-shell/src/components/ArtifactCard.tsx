import { Download, FileText, Image as ImageIcon, ShieldCheck } from 'lucide-react';
import type { VerifiedArtifact } from '../api/types';

interface ArtifactCardProps {
  artifact: VerifiedArtifact;
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} Б`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} КБ`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} МБ`;
}

export function ArtifactCard({ artifact }: ArtifactCardProps) {
  const isImage = artifact.mimeType.startsWith('image/');
  const preview = artifact.previewUrl ?? (isImage ? artifact.downloadUrl : undefined);

  return (
    <article className="artifact-card" data-testid="verified-artifact">
      {preview ? (
        <img className="artifact-preview" src={preview} alt={artifact.name} />
      ) : (
        <div className="artifact-file-icon" aria-hidden="true">
          {isImage ? <ImageIcon /> : <FileText />}
        </div>
      )}
      <div className="artifact-copy">
        <span className="artifact-verified"><ShieldCheck aria-hidden="true" /> Проверено</span>
        <strong>{artifact.name}</strong>
        <small>{artifact.mimeType} · {formatSize(artifact.sizeBytes)} · {artifact.sha256.slice(0, 10)}…</small>
      </div>
      <a className="artifact-download" href={artifact.downloadUrl} download={artifact.name} aria-label={`Скачать ${artifact.name}`}>
        <Download aria-hidden="true" />
      </a>
    </article>
  );
}
