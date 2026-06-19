import { useState } from "react";
import { FileText, Maximize2, Minimize2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { renderMarkdown } from "@/lib/markdown";
import { normalizeDocumentMarkdown, extractDocumentTitle, countDocumentSections } from "./documentUtils";

export function DocumentView({ content }: { content: string }) {
  const normalizedContent = normalizeDocumentMarkdown(content);
  const [expanded, setExpanded] = useState(false);
  const stats = countDocumentSections(normalizedContent);

  return (
    <section className={cn("kolibri-document", expanded && "kolibri-document--expanded")} aria-label="Документ в чате">
      <div className="kolibri-document__bar">
        <div className="kolibri-document__badge">
          <FileText className="h-4 w-4" />
          Документ
        </div>
        <div className="kolibri-document__title">{extractDocumentTitle(normalizedContent)}</div>
        <button
          type="button"
          className="kolibri-document__toggle"
          onClick={() => setExpanded((value) => !value)}
          aria-expanded={expanded}
        >
          {expanded ? <Minimize2 className="h-3.5 w-3.5" /> : <Maximize2 className="h-3.5 w-3.5" />}
          {expanded ? "Свернуть" : "Открыть"}
        </button>
      </div>
      <div className="kolibri-document__meta" aria-label="Структура документа">
        <span>{stats.headings || 1} разделов</span>
        <span>{stats.listItems} пунктов</span>
        {stats.tableRows ? <span>{stats.tableRows} строк таблиц</span> : null}
      </div>
      <div className="kolibri-document__page">
        <div className="markdown document-markdown" dangerouslySetInnerHTML={{ __html: renderMarkdown(normalizedContent) }} />
      </div>
      {!expanded ? (
        <div className="kolibri-document__fade">
          <button type="button" onClick={() => setExpanded(true)}>
            Развернуть документ
          </button>
        </div>
      ) : null}
    </section>
  );
}
