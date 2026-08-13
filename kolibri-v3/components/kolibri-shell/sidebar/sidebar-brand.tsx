"use client";

import { PetAvatar } from "@/components/kolibri-shell/kolibri-pet";

export function SidebarBrand() {
	return (
		<div
			data-slot="workspace-sidebar-brand"
			className="flex min-w-0 items-center gap-2 pl-2"
		>
			<div className="flex min-w-0 items-center">
				<PetAvatar className="size-9" id="kolibri" />
				<span className="ml-1.5 truncate text-[15px] font-semibold tracking-[-0.02em]">
					КолИ
				</span>
			</div>
		</div>
	);
}
