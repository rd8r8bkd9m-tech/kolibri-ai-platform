import { PanelLeft } from "lucide-react";
import { SidebarChromeButton } from "@/components/kolibri-shell/sidebar/sidebar-controls";

type SidebarChromeProps = {
	isOverlay: boolean;
	onRequestClose?: () => void;
};

export function SidebarChrome({
	isOverlay,
	onRequestClose,
}: SidebarChromeProps) {
	return (
		<div
			data-slot="workspace-sidebar-chrome"
			className="flex shrink-0 items-center"
		>
			<SidebarChromeButton
				label={isOverlay ? "Закрыть навигацию" : "Переключить боковую панель"}
				shortcut="⌘B"
				onClick={onRequestClose}
				disabled={!onRequestClose}
			>
				{isOverlay ? (
					<span
						data-slot="mobile-hamburger-icon"
						aria-hidden="true"
						className="flex w-6 flex-col gap-[7px]"
					>
						<span className="h-[2.5px] w-full rounded-full bg-current" />
						<span className="h-[2.5px] w-full rounded-full bg-current" />
					</span>
				) : (
					<PanelLeft aria-hidden="true" className="size-[18px]" />
				)}
			</SidebarChromeButton>
		</div>
	);
}
