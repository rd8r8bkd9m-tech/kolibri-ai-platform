export function isDocumentLike(content: string) {
  const text = content.trim();
  if (text.length < 260) return false;

  const headingCount = (text.match(/^#{1,3}\s+\S/gm) ?? []).length;
  const inlineHeadings = (text.match(/(?:^|\s)#{2,3}\s+\S/g) ?? []).length;
  const numberedItems = (text.match(/^\s*\d+\.\s+\S/gm) ?? []).length;
  const bulletItems = (text.match(/^\s*[-*]\s+\S/gm) ?? []).length;
  const inlineChecklistItems = (text.match(/[-*]\s+\[[ xX]\]\s+\S/g) ?? []).length;
  const tableRows = (text.match(/^\|.+\|$/gm) ?? []).length;
  const documentWords = /\b(отч[её]т|документ|план|техническ(?:ий|ого)|регламент|инструкция|резюме|контроль качества|основная часть)\b/i.test(text);

  return (
    headingCount >= 2 ||
    inlineHeadings >= 2 ||
    tableRows >= 2 ||
    numberedItems >= 4 ||
    inlineChecklistItems >= 2 ||
    (documentWords && (headingCount + inlineHeadings >= 1 || bulletItems >= 3 || text.length > 900))
  );
}

export function normalizeDocumentMarkdown(content: string) {
  return content
    .replace(/\s+(#{2,3}\s+\S)/g, "\n\n$1")
    .replace(
      /^(#{2,3}\s+(?:Резюме|Архитектура процесса|Контроль качества и проверки|Проверки|План|Итог|Вывод|Основная часть|Рекомендации))\s+/gim,
      "$1\n\n",
    )
    .replace(/\s+(\d+\.\s+\*\*[^*]+:\*\*)/g, "\n\n$1")
    .replace(/\s+(\d+\.\s+\S)/g, "\n\n$1")
    .replace(/\s+([-*]\s+\[[ xX]\]\s+\S)/g, "\n$1")
    .replace(/\s+([-*]\s+\S)/g, "\n$1")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

export function extractDocumentTitle(content: string) {
  const normalized = normalizeDocumentMarkdown(content);
  const firstHeading = normalized.match(/^#\s+(.+)$/m);
  if (firstHeading?.[1]) return firstHeading[1].trim();

  const firstLine = normalized
    .split("\n")
    .map((line) => line.trim())
    .find((line) => line.length > 0);

  if (!firstLine) return "Документ Kolibri";
  return firstLine.replace(/^#+\s*/, "").replace(/\s+#{2,3}\s+.*$/, "").slice(0, 90);
}

export function countDocumentSections(content: string) {
  const headings = (content.match(/^#{1,3}\s+\S/gm) ?? []).length;
  const listItems = (content.match(/^\s*(?:[-*]|\d+\.)\s+\S/gm) ?? []).length;
  const tableRows = (content.match(/^\|.+\|$/gm) ?? []).length;
  return { headings, listItems, tableRows };
}
