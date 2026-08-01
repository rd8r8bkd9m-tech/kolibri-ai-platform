"use client";

import type { ToolCallMessagePartComponent } from "@assistant-ui/react";
import { ProductToolStatus } from "./tool-fallback/tool-status";

export const ToolFallback: ToolCallMessagePartComponent = ({
	toolName,
	status,
}) => <ProductToolStatus toolName={toolName} status={status} />;
