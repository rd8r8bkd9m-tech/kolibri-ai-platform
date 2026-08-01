"use client";

import { useAuiState } from "@assistant-ui/react";
import { FileText } from "lucide-react";
import { type FC, type PropsWithChildren, useState } from "react";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import {
	Dialog,
	DialogContent,
	DialogTitle,
	DialogTrigger,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import { useAttachmentSrc } from "./attachment-hooks";

const AttachmentPreview: FC<{ src: string }> = ({ src }) => {
	const [isLoaded, setIsLoaded] = useState(false);
	const name = useAuiState((s) => s.attachment.name);

	return (
		<img
			src={src}
			alt={`Предпросмотр вложения «${name}»`}
			className={cn(
				"block h-auto max-h-[80vh] w-auto max-w-full rounded-sm object-contain transition-opacity duration-300 motion-reduce:transition-none",
				isLoaded
					? "aui-attachment-preview-image-loaded opacity-100"
					: "aui-attachment-preview-image-loading opacity-0",
			)}
			onLoad={() => setIsLoaded(true)}
		/>
	);
};

export const AttachmentPreviewDialog: FC<PropsWithChildren> = ({
	children,
}) => {
	const src = useAttachmentSrc();
	const name = useAuiState((s) => s.attachment.name);

	if (!src) return children;

	return (
		<Dialog>
			<DialogTrigger
				className="aui-attachment-preview-trigger cursor-zoom-in"
				asChild
			>
				{children}
			</DialogTrigger>
			<DialogContent className="aui-attachment-preview-dialog-content [&>button]:bg-foreground/60 [&>button]:hover:bg-foreground/80 [&_svg]:text-background p-2 sm:max-w-3xl [&>button]:rounded-full [&>button]:p-1 [&>button]:opacity-100 [&>button]:ring-0!">
				<DialogTitle className="aui-sr-only sr-only">
					Предпросмотр изображения «{name}»
				</DialogTitle>
				<div className="aui-attachment-preview bg-background relative mx-auto flex max-h-[80dvh] w-full items-center justify-center overflow-hidden rounded-sm">
					<AttachmentPreview src={src} />
				</div>
			</DialogContent>
		</Dialog>
	);
};

export const AttachmentThumb: FC = () => {
	const src = useAttachmentSrc();
	const name = useAuiState((s) => s.attachment.name);

	return (
		<Avatar className="aui-attachment-tile-avatar h-full w-full rounded-none">
			<AvatarImage
				src={src}
				alt={`Предпросмотр вложения «${name}»`}
				className="aui-attachment-tile-image object-cover"
			/>
			<AvatarFallback>
				<FileText className="aui-attachment-tile-fallback-icon text-muted-foreground/80 size-6 stroke-[1.5]" />
			</AvatarFallback>
		</Avatar>
	);
};
