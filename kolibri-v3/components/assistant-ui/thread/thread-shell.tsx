"use client";

import { type CSSProperties, type PropsWithChildren } from "react";

import { uiClassTokens } from "@/components/ui/class-names";

type ThreadShellStyle = CSSProperties & Record<string, string>;

type ThreadShellProps = PropsWithChildren<{
	className?: string;
	compact: boolean;
	isRunning: boolean;
	style?: ThreadShellStyle;
}>;

export const ThreadShell = ({
	children,
	className,
	compact,
	isRunning,
	style,
}: ThreadShellProps) => {
	return (
		<div
			aria-busy={isRunning}
			data-mobile-layout={compact ? "true" : "false"}
			className={className ?? uiClassTokens.threadRoot}
			style={style}
		>
			{children}
		</div>
	);
};
