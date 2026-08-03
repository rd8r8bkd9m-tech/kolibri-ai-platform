"use client";

import type { ToolCallMessagePartComponent } from "@assistant-ui/react";
import { ProductToolStatus } from "./tool-fallback/tool-status";
import { Button } from "@/components/ui/button";

export const ToolApprovalActions: ToolCallMessagePartComponent = ({
	approval,
	respondToApproval,
}) => {
	if (!approval || approval.approved !== undefined || approval.resolution) return null;
	return (
		<div className="border-amber-500/40 bg-amber-500/10 mt-2 flex flex-wrap items-center gap-2 rounded-md border p-2 text-xs">
			<span>{approval.reason ?? "Требуется подтверждение"}</span>
			<Button type="button" size="sm" onClick={() => respondToApproval({ approved: true })}>
				Разрешить
			</Button>
			<Button type="button" size="sm" variant="outline" onClick={() => respondToApproval({ approved: false })}>
				Отклонить
			</Button>
		</div>
	);
};

export const ToolFallback: ToolCallMessagePartComponent = ({ toolName, status, ...props }) => (
	<div className="space-y-2">
		<ProductToolStatus toolName={toolName} status={status} />
		<ToolApprovalActions toolName={toolName} status={status} {...props} />
	</div>
);
