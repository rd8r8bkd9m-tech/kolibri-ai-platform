import type { ReactNode } from "react";
import { StyleSheet } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { NativeScreenHeader } from "@/components/shell/native-screen-header";
import { useTheme } from "@/hooks/use-theme";

type NativeScreenShellProps = {
	backgroundColor?: string;
	children: ReactNode;
	onBack: () => void;
	subtitle?: string;
	title: string;
	trailing?: ReactNode;
};

export function NativeScreenShell({
	backgroundColor,
	children,
	onBack,
	subtitle,
	title,
	trailing,
}: NativeScreenShellProps) {
	const { colors } = useTheme();
	return (
		<SafeAreaView
			edges={["top", "bottom"]}
			style={[
				styles.safe,
				{ backgroundColor: backgroundColor ?? colors.background },
			]}
		>
			<NativeScreenHeader
				onBack={onBack}
				subtitle={subtitle}
				title={title}
				trailing={trailing}
			/>
			{children}
		</SafeAreaView>
	);
}

const styles = StyleSheet.create({
	safe: { flex: 1 },
});
