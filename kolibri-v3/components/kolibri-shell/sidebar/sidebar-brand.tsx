export function SidebarBrand() {
	return (
		<div
			data-slot="workspace-sidebar-brand"
			className="flex h-12 shrink-0 items-center pr-2 pl-3.5"
		>
			<div className="flex min-w-0 items-center">
				<span className="truncate text-[17px] font-semibold tracking-[-0.02em]">
					Птичка
				</span>
			</div>
		</div>
	);
}
