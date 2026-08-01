"use client";

import { ComposerPrimitive, MessagePrimitive } from "@assistant-ui/react";
import { type FC } from "react";
import { AttachmentUI } from "./attachment-ui";

export const UserMessageAttachments: FC = () => {
	return (
		<div className="aui-user-message-attachments-end col-span-full col-start-1 row-start-1 flex w-full flex-row justify-end gap-2">
			<MessagePrimitive.Attachments>
				{() => <AttachmentUI />}
			</MessagePrimitive.Attachments>
		</div>
	);
};

export const ComposerAttachments: FC = () => {
	return (
		<div className="aui-composer-attachments flex w-full flex-row items-center gap-2 overflow-x-auto empty:hidden">
			<ComposerPrimitive.Attachments>
				{() => <AttachmentUI />}
			</ComposerPrimitive.Attachments>
		</div>
	);
};
