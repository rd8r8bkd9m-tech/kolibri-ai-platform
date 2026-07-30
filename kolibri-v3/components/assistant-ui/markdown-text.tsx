"use client";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  StreamdownTextPrimitive,
  type MermaidErrorComponentProps,
  type StreamdownTextPrimitiveProps,
} from "@assistant-ui/react-streamdown";
import { cjk } from "@streamdown/cjk";
import { code } from "@streamdown/code";
import { math } from "@streamdown/math";
import { createMermaidPlugin } from "@streamdown/mermaid";
import type { MermaidConfig } from "mermaid";
import type { StreamdownProps, UrlTransform } from "streamdown";
import { memo, type FC } from "react";

const MERMAID_CONFIG: MermaidConfig = {
  startOnLoad: false,
  securityLevel: "strict",
  maxTextSize: 12_000,
  maxEdges: 200,
  htmlLabels: false,
  theme: "neutral",
  secure: [
    "securityLevel",
    "startOnLoad",
    "maxTextSize",
    "maxEdges",
    "secure",
  ],
};

const MERMAID_PLUGIN = createMermaidPlugin({
  config: MERMAID_CONFIG,
});

const RICH_TEXT_PLUGINS = {
  cjk,
  code,
  math,
  mermaid: MERMAID_PLUGIN,
} as const;

// @assistant-ui/react-streamdown 0.3 narrows `code` to boolean even though
// Streamdown 2.5 supports independent copy/download controls at runtime.
const RICH_TEXT_CONTROLS = {
  table: false,
  code: {
    copy: true,
    download: false,
  },
  mermaid: {
    copy: true,
    download: true,
    fullscreen: false,
    panZoom: false,
  },
} satisfies NonNullable<StreamdownProps["controls"]>;

const RUSSIAN_CONTROLS = {
  close: "Закрыть",
  copied: "Скопировано",
  copyCode: "Копировать код",
  copyLink: "Копировать ссылку",
  downloadDiagram: "Скачать диаграмму",
  downloadDiagramAsMmd: "Скачать исходник Mermaid",
  downloadDiagramAsPng: "Скачать диаграмму в PNG",
  downloadDiagramAsSvg: "Скачать диаграмму в SVG",
  exitFullscreen: "Выйти из полноэкранного режима",
  externalLinkWarning: "Ссылка откроется на внешнем сайте.",
  openExternalLink: "Открыть внешнюю ссылку?",
  openLink: "Открыть ссылку",
  viewFullscreen: "Открыть диаграмму на весь экран",
} as const;

const restrictMarkdownUrl: UrlTransform = (url, key) => {
  if (key !== "href") return null;

  try {
    const protocol = new URL(url).protocol;
    return protocol === "https:" || protocol === "mailto:" ? url : null;
  } catch {
    return null;
  }
};

const MermaidError: FC<MermaidErrorComponentProps> = ({ retry }) => (
  <div
    className="border-border bg-muted/35 my-3 rounded-lg border px-4 py-3"
    role="alert"
  >
    <p className="text-sm font-medium">Не удалось построить диаграмму.</p>
    <p className="text-muted-foreground mt-1 text-sm">
      Проверьте синтаксис Mermaid или сократите схему.
    </p>
    <button
      className="border-border bg-background hover:bg-accent mt-3 rounded-md border px-2.5 py-1.5 text-xs font-medium transition-colors"
      onClick={retry}
      type="button"
    >
      Повторить
    </button>
  </div>
);

function ExternalLinkSafetyDialog({
  isOpen,
  onClose,
  onConfirm,
  url,
}: {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void;
  url: string;
}) {
  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent
        className="sm:max-w-md"
        aria-describedby="streamdown-external-link-description"
      >
        <DialogHeader>
          <DialogTitle>Открыть внешнюю ссылку?</DialogTitle>
          <DialogDescription id="streamdown-external-link-description">
            Ссылка ведёт за пределы Kolibri. Проверьте адрес перед переходом.
          </DialogDescription>
        </DialogHeader>
        <p className="max-h-32 overflow-auto break-all rounded-lg border bg-muted/35 p-3 font-mono text-xs">
          {url}
        </p>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={onClose}>
            Отмена
          </Button>
          <Button
            type="button"
            onClick={() => {
              onConfirm();
              onClose();
            }}
          >
            Открыть ссылку
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

const MarkdownTextImpl = () => (
  <StreamdownTextPrimitive
    mode="streaming"
    defer
    smooth={false}
    animated={false}
    plugins={RICH_TEXT_PLUGINS}
    shikiTheme={["github-light", "github-dark"]}
    controls={
      RICH_TEXT_CONTROLS as unknown as StreamdownTextPrimitiveProps["controls"]
    }
    lineNumbers={false}
    mermaid={{
      config: MERMAID_CONFIG,
      errorComponent: MermaidError,
    }}
    security={{
      allowedLinkPrefixes: ["https://", "mailto:"],
      allowedImagePrefixes: [],
      allowedProtocols: ["https", "mailto"],
      allowDataImages: false,
      defaultOrigin: "https://kolibriai.ru",
      blockedLinkClass: "aui-md-blocked-link",
      blockedImageClass: "aui-md-blocked-image",
    }}
    linkSafety={{
      enabled: true,
      renderModal: (props) => <ExternalLinkSafetyDialog {...props} />,
    }}
    allowedTags={{}}
    disallowedElements={["img"]}
    skipHtml
    remarkRehypeOptions={{ allowDangerousHtml: false }}
    urlTransform={restrictMarkdownUrl}
    translations={RUSSIAN_CONTROLS}
    containerClassName="aui-markdown-text"
    className="aui-md aui-streamdown text-[15px] leading-7 text-foreground [&_a]:font-medium [&_a]:text-foreground [&_a]:underline [&_a]:decoration-border [&_a]:underline-offset-4 [&_blockquote]:border-s-2 [&_blockquote]:border-border [&_blockquote]:ps-4 [&_blockquote]:text-muted-foreground [&_h1]:text-xl [&_h1]:font-semibold [&_h2]:text-lg [&_h2]:font-semibold [&_h3]:text-base [&_h3]:font-semibold [&_hr]:border-border [&_li]:my-0.5 [&_ol]:ps-5 [&_p]:my-2.5 [&_strong]:font-semibold [&_ul]:ps-5"
  />
);

export const MarkdownText = memo(MarkdownTextImpl);
