import type { DrawerContentComponentProps } from "expo-router/build/react-navigation/drawer/types";
import { useState } from "react";

import { haptics } from "@/lib/haptics";
import { releaseWebFocus } from "@/src/accessibility/release-web-focus";
import { ContextMenu } from "@/src/components/overlays/ContextMenu";
import { ProjectSheet } from "@/src/components/overlays/ProjectSheet";
import { Sidebar } from "@/src/components/overlays/Sidebar";
import { LegacyWrapper } from "@/src/components/LegacyWrapper";
import type { ThreadActionItem } from "@/src/data/pinned";
import { useAui } from "@assistant-ui/react-native";

export function DrawerContentAdapter({ navigation }: DrawerContentComponentProps) {
	const aui = useAui();
	const [menu, setMenu] = useState<{
		item: ThreadActionItem;
		anchor: { x: number; y: number };
	} | null>(null);
	const [sheetOpen, setSheetOpen] = useState(false);

	const closeDrawer = () => {
		releaseWebFocus();
		navigation.closeDrawer();
	};

	return (
		<>
			<Sidebar
				onClose={closeDrawer}
				onOpenContextMenu={(item, anchor) => {
					haptics.medium();
					setMenu({ item, anchor });
				}}
				onOpenSheet={() => {
					closeDrawer();
					setSheetOpen(true);
				}}
			/>
			<ContextMenu
				anchor={menu?.anchor ?? null}
				item={menu?.item ?? null}
				onClose={() => setMenu(null)}
				onNewProject={() => {
					closeDrawer();
					setSheetOpen(true);
				}}
			/>
			<LegacyWrapper>
				<ProjectSheet
					onClose={() => setSheetOpen(false)}
					onCreate={() => aui.threads.switchToNewThread()}
					visible={sheetOpen}
				/>
			</LegacyWrapper>
		</>
	);
}
