"use client";

import { AttachmentPrimitive, useAui, useAuiState } from "@assistant-ui/react";
import { AlertCircleIcon, Loader2Icon } from "lucide-react";
import { type FC } from "react";
import {
	Tooltip,
	TooltipContent,
	TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { AttachmentRemove } from "./attachment-controls";
import { AttachmentPreviewDialog, AttachmentThumb } from "./attachment-preview";

export const AttachmentUI: FC = () => {
	const aui = useAui();
	const isComposer = aui.attachment.source !== "message";

	const isImage = useAuiState((s) => s.attachment.type === "image");
	const name = useAuiState((s) => s.attachment.name);
	const typeLabel = useAuiState((s) => {
		switch (s.attachment.type) {
			case "image":
				return "Изображение";
			case "document":
				return "Документ";
			case "file":
				return "Файл";
			default:
				return s.attachment.type;
		}
	});

	const uploadState = useAuiState((s) =>
		s.attachment.status.type === "running"
			? "uploading"
			: s.attachment.status.type === "incomplete" &&
					s.attachment.status.reason === "error"
				? "error"
				: undefined,
	);
	const isUploading = uploadState === "uploading";
	const isError = uploadState === "error";

	const errorMessage = useAuiState((s) =>
		s.attachment.status.type === "incomplete" &&
		s.attachment.status.reason === "error"
			? (s.attachment.status.message ?? "Не удалось загрузить файл")
			: undefined,
	);

	return (
		<Tooltip>
			<AttachmentPrimitive.Root
				className={cn(
					"aui-attachment-root relative",
					isComposer &&
						"animate-in fade-in-0 zoom-in-95 duration-200 motion-reduce:animate-none",
					isImage &&
						!isComposer &&
						"aui-attachment-root-message only:*:first:size-24",
				)}
			>
				<AttachmentPreviewDialog>
					<TooltipTrigger asChild>
						<div
							className={cn(
								"aui-attachment-tile bg-muted relative overflow-hidden outline-none after:pointer-events-none after:absolute after:inset-0 after:rounded-[inherit] after:ring-1 after:ring-black/10 after:transition-colors after:ring-inset dark:after:ring-white/10",
								isImage &&
									"hover:after:bg-foreground/10 focus-visible:ring-ring/50 cursor-pointer transition-transform focus-visible:ring-3 active:scale-[0.96] motion-reduce:transition-none",
								isComposer
									? "size-20 rounded-[11px]"
									: "size-14 rounded-[calc(var(--composer-radius)-var(--composer-padding))]",
								isError &&
									"after:ring-destructive/60 dark:after:ring-destructive/60",
							)}
							role={isImage ? "button" : "group"}
							tabIndex={isImage ? 0 : undefined}
							onKeyDown={(e) => {
								if (!isImage) return;
								if (e.key === "Enter") {
									e.preventDefault();
									e.currentTarget.click();
								} else if (e.key === " ") {
									e.preventDefault();
								}
							}}
							onKeyUp={(e) => {
								if (isImage && e.key === " ") e.currentTarget.click();
							}}
							aria-label={`${typeLabel} «${name}»${
								isError
									? ", загрузка не удалась"
									: isUploading
										? ", загружается"
										: ""
							}`}
						>
							<AttachmentThumb />
							{isUploading && (
								<div
									aria-hidden="true"
									className="aui-attachment-tile-uploading bg-background/90 animate-in fade-in-0 absolute inset-0 flex items-center justify-center motion-reduce:animate-none"
								>
									<Loader2Icon className="text-muted-foreground size-4 animate-spin" />
								</div>
							)}
							{isError && (
								<div
									aria-hidden="true"
									className="aui-attachment-tile-error bg-background/95 animate-in fade-in-0 absolute inset-0 flex items-center justify-center motion-reduce:animate-none"
								>
									<AlertCircleIcon className="text-destructive size-4" />
								</div>
							)}
						</div>
					</TooltipTrigger>
				</AttachmentPreviewDialog>
				{isComposer && <AttachmentRemove />}
			</AttachmentPrimitive.Root>
			<TooltipContent side="top">
				<AttachmentPrimitive.Name />
				{errorMessage && (
					<p className="aui-attachment-error-message">{errorMessage}</p>
				)}
			</TooltipContent>
		</Tooltip>
	);
};
