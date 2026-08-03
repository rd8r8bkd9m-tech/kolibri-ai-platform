import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

function PanelSkeleton({ rows = 4, className }: { rows?: number; className?: string }) {
	return (
		<div
			role="status"
			aria-label="Загрузка данных"
			className={cn("flex flex-col gap-3 p-4", className)}
		>
			<Skeleton className="h-4 w-1/3" />
			<Skeleton className="h-3 w-2/3" />
			<div className="mt-2 flex flex-col gap-2">
				{Array.from({ length: rows }, (_, i) => (
					<Skeleton key={i} className="h-8 w-full" />
				))}
			</div>
		</div>
	);
}

function FileTreeSkeleton({ rows = 6 }: { rows?: number }) {
	return (
		<div
			role="status"
			aria-label="Загрузка файлов"
			className="flex flex-col gap-1 p-3"
		>
			{Array.from({ length: rows }, (_, i) => (
				<div key={i} className="flex items-center gap-2">
					<Skeleton className="size-4 shrink-0" />
					<Skeleton
						className="h-3.5"
						style={{ width: `${40 + Math.random() * 40}%` }}
					/>
				</div>
			))}
		</div>
	);
}

function CardListSkeleton({ rows = 3 }: { rows?: number }) {
	return (
		<div
			role="status"
			aria-label="Загрузка списка"
			className="flex flex-col gap-2 p-3"
		>
			{Array.from({ length: rows }, (_, i) => (
				<div
					key={i}
					className="border-border/70 flex items-center gap-3 rounded-lg border p-3"
				>
					<Skeleton className="size-9 shrink-0 rounded-lg" />
					<div className="flex flex-1 flex-col gap-1.5">
						<Skeleton className="h-3.5 w-2/3" />
						<Skeleton className="h-3 w-1/3" />
					</div>
				</div>
			))}
		</div>
	);
}

function TableSkeleton({
	rows = 4,
	columns = 3,
}: {
	rows?: number;
	columns?: number;
}) {
	return (
		<div
			role="status"
			aria-label="Загрузка таблицы"
			className="flex flex-col gap-0"
		>
			<div className="border-border/70 flex items-center gap-3 border-b px-3.5 py-2">
				{Array.from({ length: columns }, (_, i) => (
					<Skeleton
						key={i}
						className="h-3"
						style={{ width: `${100 / columns}%` }}
					/>
				))}
			</div>
			{Array.from({ length: rows }, (_, i) => (
				<div
					key={i}
					className="border-border/40 flex items-center gap-3 border-b px-3.5 py-2.5"
				>
					{Array.from({ length: columns }, (_, j) => (
						<Skeleton
							key={j}
							className="h-3"
							style={{ width: `${50 + Math.random() * 30}%` }}
						/>
					))}
				</div>
			))}
		</div>
	);
}

export { CardListSkeleton, FileTreeSkeleton, PanelSkeleton, TableSkeleton };
