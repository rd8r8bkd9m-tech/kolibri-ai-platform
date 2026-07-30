"use client";

import { EstimateDocumentSurface } from "@/components/assistant-ui/product-widgets";
import { useAssistantContext, useAui } from "@assistant-ui/react";
import {
  ArrowLeft,
  ChevronRight,
  FileArchive,
  FileImage,
  FileSignature,
  FileSpreadsheet,
  FileText,
  Folder,
  Sparkles,
  type LucideIcon,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import type {
  WorkspaceFile,
  WorkspaceFileKind,
} from "./workspace-file-manager";

const FILE_KIND_ICON: Record<WorkspaceFileKind, LucideIcon> = {
  attachment: FileArchive,
  contract: FileSignature,
  document: FileText,
  drawing: FileImage,
  estimate: FileSpreadsheet,
};

export function WorkspaceArtifactEditor({
  compactChrome = false,
  file,
  onBack,
  projectLabel,
}: {
  compactChrome?: boolean;
  file: WorkspaceFile;
  onBack: () => void;
  projectLabel: string;
}) {
  const PreviewIcon = FILE_KIND_ICON[file.kind];

  useAssistantContext({
    getContext: () =>
      [
        `Open project file: ${file.name}.`,
        `Project: ${projectLabel}.`,
        `Kind: ${file.kind}. Status: ${file.status}.`,
        "The file body has not been loaded into Canvas.",
      ].join("\n"),
  });

  if (file.kind === "estimate" && file.projectId) {
    return (
      <section className="flex min-h-0 flex-1 flex-col">
        {!compactChrome ? (
          <ArtifactToolbar
            file={file}
            onBack={onBack}
            projectLabel={file.projectName || projectLabel}
          />
        ) : null}
        <div
          data-slot="mobile-artifact-scroll"
          className="min-h-0 flex-1 overflow-x-hidden overflow-y-auto bg-muted/10 p-3 @min-[700px]:p-5"
        >
          <EstimateDocumentSurface projectId={file.projectId} />
        </div>
      </section>
    );
  }

  return (
    <section className="flex min-h-0 flex-1 flex-col">
      {!compactChrome ? (
        <ArtifactToolbar
          file={file}
          onBack={onBack}
          projectLabel={projectLabel}
        />
      ) : null}
      <div className="bg-muted/15 flex min-h-0 flex-1 items-center justify-center p-6">
        <div className="text-muted-foreground flex max-w-sm flex-col items-center text-center">
          <span className="border-border bg-background mb-4 grid size-12 place-items-center rounded-xl border">
            <PreviewIcon className="size-5" aria-hidden="true" />
          </span>
          <h2 className="text-foreground text-sm font-medium">{file.name}</h2>
          <p className="mt-1.5 text-xs leading-relaxed">
            Содержимое ещё не загружено в рабочую область. Редактор станет
            доступен после получения версии файла из хранилища проекта.
          </p>
          <p className="mt-4 text-[10px]">
            {file.size} · {file.status}
          </p>
        </div>
      </div>
    </section>
  );
}

function ArtifactToolbar({
  file,
  onBack,
  projectLabel,
}: {
  file: WorkspaceFile;
  onBack: () => void;
  projectLabel: string;
}) {
  const aui = useAui();

  return (
    <header className="border-border/80 flex h-11 shrink-0 items-center gap-1 border-b px-2">
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            type="button"
            variant="ghost"
            size="icon-xs"
            className="size-7 rounded-lg"
            onClick={onBack}
            aria-label="Вернуться к файлам"
          >
            <ArrowLeft aria-hidden="true" />
          </Button>
        </TooltipTrigger>
        <TooltipContent side="bottom" sideOffset={6}>
          Назад к файлам
        </TooltipContent>
      </Tooltip>

      <div className="text-muted-foreground ml-1 flex min-w-0 items-center gap-1.5 text-[11px]">
        <Folder className="size-3.5 shrink-0" aria-hidden="true" />
        <span className="hidden max-w-28 truncate @min-[560px]:inline">
          {projectLabel}
        </span>
        <ChevronRight
          className="hidden size-3 shrink-0 @min-[560px]:block"
          aria-hidden="true"
        />
        <span className="text-foreground truncate font-medium">{file.name}</span>
      </div>

      <span className="text-muted-foreground ml-auto hidden text-[10px] @min-[460px]:inline">
        {file.status}
      </span>

      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            type="button"
            variant="ghost"
            size="xs"
            className="ml-1"
            onClick={() =>
              aui
                .composer()
                .setText(
                  `Помоги с файлом «${file.name}» в проекте «${projectLabel}». Сначала проверь, доступна ли актуальная версия и связанные источники.`,
                )
            }
          >
            <Sparkles aria-hidden="true" />
            <span className="hidden @min-[620px]:inline">Спросить Kolibri</span>
            <span className="sr-only @min-[620px]:hidden">
              Спросить Kolibri об этом файле
            </span>
          </Button>
        </TooltipTrigger>
        <TooltipContent side="bottom" sideOffset={6}>
          Подготовить вопрос об этом файле
        </TooltipContent>
      </Tooltip>
    </header>
  );
}
