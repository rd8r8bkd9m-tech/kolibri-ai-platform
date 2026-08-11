"use client";

import { useMessagePartText } from "@assistant-ui/react";
import { memo } from "react";

/**
 * Renders assistant-ui composer directives (`:type[label]{name=id}`) as
 * compact chips in user messages, keeping the surrounding text plain.
 * Slash-command and mention directives produced by the composer trigger
 * popovers are shown as chips instead of raw syntax.
 */

const DIRECTIVE_RE = /:([\w-]+)\[([^\]]+)\](?:\{name=([^}]+)\})?/g;

const DIRECTIVE_META: Record<string, { label: string; className: string }> = {
	tool: {
		label: "Инструмент",
		className:
			"border-border/70 bg-muted/70 text-muted-foreground data-[kind=tool]:",
	},
	context: {
		label: "Контекст",
		className:
			"border-accent/70 bg-accent/45 text-foreground/80",
	},
	command: {
		label: "Команда",
		className:
			"border-primary/20 bg-primary/10 text-primary",
	},
};

type DirectiveSegment =
	| { kind: "text"; text: string }
	| {
			kind: "directive";
			type: string;
			label: string;
			id: string;
	  };

function parseDirectives(text: string): DirectiveSegment[] {
	const segments: DirectiveSegment[] = [];
	let lastIndex = 0;
	let match: RegExpExecArray | null;
	DIRECTIVE_RE.lastIndex = 0;
	while ((match = DIRECTIVE_RE.exec(text)) !== null) {
		if (match.index > lastIndex) {
			segments.push({ kind: "text", text: text.slice(lastIndex, match.index) });
		}
		segments.push({
			kind: "directive",
			type: match[1],
			label: match[2],
			id: match[3] ?? match[2],
		});
		lastIndex = match.index + match[0].length;
	}
	if (lastIndex < text.length) {
		segments.push({ kind: "text", text: text.slice(lastIndex) });
	}
	return segments;
}

function DirectiveChip({
	type,
	label,
}: {
	type: string;
	label: string;
}) {
	const meta = DIRECTIVE_META[type];
	const chipLabel = meta?.label ?? type;
	return (
		<span
			data-kind={type}
			className={`inline-flex max-w-full items-center gap-1 rounded-md border px-1.5 py-0.5 align-baseline text-[12px] font-medium leading-4 ${
				meta?.className ?? DIRECTIVE_META.tool.className
			}`}
			title={label}
		>
			<span className="truncate">{label}</span>
			<span className="shrink-0 opacity-70">{chipLabel}</span>
		</span>
	);
}

const DirectiveTextImpl = () => {
	const { text } = useMessagePartText();
	const segments = parseDirectives(text);
	const hasDirectives = segments.some((segment) => segment.kind === "directive");
	if (!hasDirectives) {
		return <span className="whitespace-pre-wrap break-words">{text}</span>;
	}
	return (
		<span className="flex flex-wrap items-center gap-x-1.5 gap-y-1 whitespace-pre-wrap break-words">
			{segments.map((segment, index) =>
				segment.kind === "text" ? (
					<span key={index}>{segment.text}</span>
				) : (
					<DirectiveChip
						key={index}
						type={segment.type}
						label={segment.label}
					/>
				),
			)}
		</span>
	);
};

export const DirectiveText = memo(DirectiveTextImpl);
