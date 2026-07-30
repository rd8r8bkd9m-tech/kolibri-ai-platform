"use client";

import { Button } from "@/components/ui/button";
import {
  BookOpen,
  ChevronRight,
  FileText,
  FolderKanban,
  Globe,
  LayoutDashboard,
} from "lucide-react";
import type { WorkspaceFile } from "./workspace-file-manager";

export function WorkspaceDesktop({
  onOpenBrowser,
  onOpenDocuments,
  onOpenFile,
  onOpenProjects,
  onOpenReferences,
  recentFiles,
}: {
  onOpenBrowser: () => void;
  onOpenDocuments: () => void;
  onOpenFile: (file: WorkspaceFile) => void;
  onOpenProjects: () => void;
  onOpenReferences: () => void;
  recentFiles: readonly WorkspaceFile[];
}) {
  return (
    <section
      aria-labelledby="workspace-desktop-title"
      className="flex min-h-0 flex-1 flex-col overflow-y-auto"
    >
      <div className="mx-auto flex w-full max-w-5xl flex-1 flex-col px-5 py-8 sm:px-8">
        <div className="flex items-start gap-3">
          <div className="bg-muted flex size-10 shrink-0 items-center justify-center rounded-xl">
            <LayoutDashboard
              aria-hidden="true"
              className="text-muted-foreground size-5"
            />
          </div>
          <div>
            <h1
              id="workspace-desktop-title"
              className="text-xl font-semibold tracking-[-0.02em]"
            >
              Рабочий стол
            </h1>
            <p className="text-muted-foreground mt-1 text-[13px] leading-5">
              Откройте нужный раздел в этой же рабочей области. Состояние
              разделов сохраняется при переключении.
            </p>
          </div>
        </div>

        <div className="mt-8 grid gap-6 lg:grid-cols-[minmax(0,1.25fr)_minmax(16rem,0.75fr)]">
          <section aria-labelledby="desktop-continue-title">
            <h2
              id="desktop-continue-title"
              className="text-muted-foreground text-[12px] font-medium"
            >
              Недавние документы
            </h2>
            {recentFiles.length > 0 ? (
              <div className="mt-2 overflow-hidden rounded-2xl border bg-card">
                {recentFiles.slice(0, 4).map((file) => (
                  <button
                    key={file.id}
                    type="button"
                    onClick={() => onOpenFile(file)}
                    className="border-border/70 hover:bg-muted/45 focus-visible:ring-ring flex min-h-14 w-full items-center gap-3 border-b px-3 text-left outline-none last:border-b-0 focus-visible:ring-2 focus-visible:ring-inset"
                  >
                    <span className="bg-muted text-muted-foreground grid size-8 shrink-0 place-items-center rounded-lg">
                      <FileText aria-hidden="true" className="size-4" />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-xs font-medium">
                        {file.name}
                      </span>
                      <span className="text-muted-foreground mt-0.5 block truncate text-[10px]">
                        {file.projectName || "Без проекта"} · {file.modifiedAt}
                      </span>
                    </span>
                    <ChevronRight
                      aria-hidden="true"
                      className="text-muted-foreground size-4 shrink-0"
                    />
                  </button>
                ))}
              </div>
            ) : (
              <div
                className="mt-2 flex min-h-44 items-center justify-center rounded-2xl border bg-card px-6 py-8 text-center"
                role="status"
              >
                <div className="max-w-xs">
                  <span className="bg-muted text-muted-foreground mx-auto grid size-10 place-items-center rounded-xl">
                    <FileText aria-hidden="true" className="size-5" />
                  </span>
                  <h3 className="mt-3 text-[13px] font-medium">
                    Недавних документов нет
                  </h3>
                  <p className="text-muted-foreground mt-1 text-[11px] leading-relaxed">
                    Созданные и загруженные документы появятся здесь
                    автоматически.
                  </p>
                </div>
              </div>
            )}
          </section>

          <section aria-labelledby="desktop-launcher-title">
            <h2
              id="desktop-launcher-title"
              className="text-muted-foreground text-[12px] font-medium"
            >
              Открыть
            </h2>
            <div className="mt-2 grid gap-2">
              <DesktopLauncherButton
                icon={FolderKanban}
                label="Проекты"
                onClick={onOpenProjects}
              />
              <DesktopLauncherButton
                icon={FileText}
                label="Документы"
                onClick={onOpenDocuments}
              />
              <DesktopLauncherButton
                icon={BookOpen}
                label="Справочники"
                onClick={onOpenReferences}
              />
              <DesktopLauncherButton
                icon={Globe}
                label="Браузер"
                onClick={onOpenBrowser}
              />
            </div>
          </section>
        </div>
      </div>
    </section>
  );
}

function DesktopLauncherButton({
  icon: Icon,
  label,
  onClick,
}: {
  icon: typeof FolderKanban;
  label: string;
  onClick: () => void;
}) {
  return (
    <Button
      type="button"
      variant="outline"
      onClick={onClick}
      className="h-10 justify-start rounded-xl px-3 shadow-none"
    >
      <Icon aria-hidden="true" className="text-muted-foreground size-4" />
      {label}
    </Button>
  );
}
