"use client";

import { AttachmentPrimitive } from "@assistant-ui/react";
import { XIcon } from "lucide-react";
import { type FC } from "react";
import { TooltipIconButton } from "@/components/assistant-ui/tooltip-icon-button";

export const AttachmentRemove: FC = () => {
	return (
		<AttachmentPrimitive.Remove asChild>
			<TooltipIconButton
				tooltip="Удалить файл"
				aria-label="Удалить файл"
				className="aui-attachment-tile-remove absolute end-1 top-1 size-5 rounded-full bg-black/70! text-white after:absolute after:-inset-1.5 hover:bg-black/85! hover:text-white! active:scale-[0.96] motion-reduce:transition-none"
				side="top"
			>
				<XIcon className="aui-attachment-remove-icon size-4 stroke-[1.9]" />
			</TooltipIconButton>
		</AttachmentPrimitive.Remove>
	);
};
