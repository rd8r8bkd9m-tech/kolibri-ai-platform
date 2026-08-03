"use client";

import {
	ChevronRight,
	File,
	FileText,
	FileSpreadsheet,
	FileImage,
	FileCode,
	Folder,
	FolderOpen,
	Upload,
	Search,
} from "lucide-react";
import { useState, useCallback, type FC } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

export interface FileTreeNode {
	id: string;
	name: string;
	type: "file" | "folder";
	children?: FileTreeNode[];
	size?: string;
	modified?: string;
	status?: "current" | "stale" | "draft";
}

interface ContextFilesTreeProps {
	files?: FileTreeNode[];
	onOpenFile?: (file: FileTreeNode) => void;
	onUpload?: () => void;
	loading?: boolean;
}

const FILE_ICONS: Record<string, FC<{ className?: string }>> = {
	pdf: FileText,
	doc: FileText,
	docx: FileText,
	xls: FileSpreadsheet,
	xlsx: FileSpreadsheet,
	csv: FileSpreadsheet,
	png: FileImage,
	jpg: FileImage,
	jpeg: FileImage,
	svg: FileImage,
	dwg: FileCode,
	dxf: FileCode,
};

function getFileIcon(name: string) {
	const ext = name.split(".").pop()?.toLowerCase() ?? "";
	return FILE_ICONS[ext] ?? File;
}

function FileTreeItem({
	node,
	depth = 0,
	onOpenFile,
}: {
	node: FileTreeNode;
	depth?: number;
	onOpenFile?: (file: FileTreeNode) => void;
}) {
	const [expanded, setExpanded] = useState(depth < 1);
	const isFolder = node.type === "folder";
	const Icon = isFolder ? (expanded ? FolderOpen : Folder) : getFileIcon(node.name);

	return (
		<div>
			<button
				type="button"
				className={cn(
					"flex w-full items-center gap-1.5 rounded-md px-2 py-1 text-xs transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring",
					!isFolder && "cursor-default",
				)}
				style={{ paddingLeft: `${depth * 16 + 8}px` }}
				onClick={() => {
					if (isFolder) {
						setExpanded(!expanded);
					} else {
						onOpenFile?.(node);
					}
				}}
			>
				{isFolder ? (
					<ChevronRight
						className={cn(
							"size-3 shrink-0 text-muted-foreground transition-transform",
							expanded && "rotate-90",
						)}
					/>
				) : (
					<span className="w-3 shrink-0" />
				)}
				<Icon className="size-3.5 shrink-0 text-muted-foreground" />
				<span className="min-w-0 truncate">{node.name}</span>
				{node.size ? (
					<span className="ml-auto shrink-0 text-[10px] text-muted-foreground tabular-nums">
						{node.size}
					</span>
				) : null}
				{node.status === "stale" ? (
					<span className="ml-1 size-1.5 shrink-0 rounded-full bg-amber-400" title="Устарел" />
				) : node.status === "draft" ? (
					<span className="ml-1 size-1.5 shrink-0 rounded-full bg-sky-400" title="Черновик" />
				) : null}
			</button>
			{isFolder && expanded && node.children?.map((child) => (
				<FileTreeItem
					key={child.id}
					node={child}
					depth={depth + 1}
					onOpenFile={onOpenFile}
				/>
			))}
		</div>
	);
}

export function ContextFilesTree({
	files = [],
	onOpenFile,
	onUpload,
}: ContextFilesTreeProps) {
	const [query, setQuery] = useState("");

	const filteredFiles = query.trim()
		? filterTree(files, query.trim().toLowerCase())
		: files;

	const handleUpload = useCallback(() => {
		onUpload?.();
	}, [onUpload]);

	return (
		<div className="flex h-full min-h-0 flex-col">
			<header className="border-border/70 flex items-center gap-1.5 border-b px-2 py-1.5">
				<div className="relative flex-1">
					<Search className="text-muted-foreground pointer-events-none absolute top-1/2 left-2 size-3 -translate-y-1/2" />
					<Input
						value={query}
						onChange={(e) => setQuery(e.target.value)}
						className="h-7 rounded-md pl-7 text-xs shadow-none"
						placeholder="Поиск"
						aria-label="Поиск файлов"
					/>
				</div>
				{onUpload ? (
					<Button
						type="button"
						variant="ghost"
						size="icon-xs"
						className="size-7"
						onClick={handleUpload}
						aria-label="Загрузить файл"
					>
						<Upload className="size-3.5" />
					</Button>
				) : null}
			</header>

			<div className="min-h-0 flex-1 overflow-y-auto p-1">
				{filteredFiles.length === 0 ? (
					<div className="flex flex-col items-center justify-center py-8 text-center">
						<Folder className="text-muted-foreground size-5" />
						<p className="text-muted-foreground mt-2 text-xs">
							{query ? "Ничего не найдено" : "Файлы не добавлены"}
						</p>
						{!query && onUpload ? (
							<Button
								type="button"
								variant="ghost"
								size="xs"
								className="mt-2"
								onClick={handleUpload}
							>
								<Upload className="size-3" />
								Загрузить
							</Button>
						) : null}
					</div>
				) : (
					filteredFiles.map((node) => (
						<FileTreeItem
							key={node.id}
							node={node}
							onOpenFile={onOpenFile}
						/>
					))
				)}
			</div>

			<footer className="border-border/70 text-muted-foreground flex shrink-0 items-center justify-between border-t px-3 py-1.5 text-[10px]">
				<span>{countFiles(files)} файлов</span>
				{files.some((f) => f.status === "stale") ? (
					<span className="flex items-center gap-1">
						<span className="size-1.5 rounded-full bg-amber-400" />
						Есть устаревшие
					</span>
				) : null}
			</footer>
		</div>
	);
}

function filterTree(nodes: FileTreeNode[], query: string): FileTreeNode[] {
	return nodes
		.map((node) => {
			if (node.type === "folder") {
				const filteredChildren = node.children
					? filterTree(node.children, query)
					: [];
				const nameMatches = node.name.toLowerCase().includes(query);
				if (nameMatches || filteredChildren.length > 0) {
					return { ...node, children: filteredChildren.length > 0 ? filteredChildren : node.children };
				}
				return null;
			}
			return node.name.toLowerCase().includes(query) ? node : null;
		})
		.filter(Boolean) as FileTreeNode[];
}

function countFiles(nodes: FileTreeNode[]): number {
	return nodes.reduce((count, node) => {
		if (node.type === "file") return count + 1;
		return count + (node.children ? countFiles(node.children) : 0);
	}, 0);
}
