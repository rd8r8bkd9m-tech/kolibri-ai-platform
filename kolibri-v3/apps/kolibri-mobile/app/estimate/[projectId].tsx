import { useLocalSearchParams, useRouter } from "expo-router";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ActivityIndicator, StyleSheet, Text, View } from "react-native";

import { NativeScreenShell } from "@/components/shell/native-screen-shell";
import { EstimateEditor } from "@/app/estimates";
import { useTheme } from "@/hooks/use-theme";
import { useMobileSession } from "@/src/auth/mobile-session";
import { ConstructionEstimateClient } from "@/src/verticals/construction-estimates/client";
import type { NativeEstimate } from "@/src/verticals/construction-estimates/contracts";
import { constructionEstimateAccess } from "@/src/verticals/construction-estimates/access";

export default function EstimateRoute() {
	const router = useRouter();
	const { projectId } = useLocalSearchParams<{ projectId?: string }>();
	const { colors } = useTheme();
	const session = useMobileSession();
	const access = constructionEstimateAccess(session.user);
	const client = useMemo(
		() => new ConstructionEstimateClient(session.authorizedFetch),
		[session.authorizedFetch],
	);
	const [estimate, setEstimate] = useState<NativeEstimate | null>(null);
	const [message, setMessage] = useState("");

	const goBack = () => {
		if (router.canGoBack()) router.back();
		else router.replace("/app?client=mobile");
	};

	const open = useCallback(async () => {
		if (!projectId) {
			setMessage("Не удалось открыть смету: не указан идентификатор проекта.");
			return;
		}
		try {
			setEstimate(await client.open(projectId));
		} catch (reason) {
			setMessage(
				reason instanceof Error
					? reason.message
					: "Не удалось открыть смету.",
			);
		}
	}, [client, projectId]);

	useEffect(() => {
		const timer = setTimeout(() => void open(), 0);
		return () => clearTimeout(timer);
	}, [open]);

	if (!access.enabled) {
		return (
			<NativeScreenShell
				onBack={goBack}
				title="Сметы"
			>
				<View style={styles.center}>
					<Text style={[styles.error, { color: colors.mutedForeground }]}>
						{access.reason}
					</Text>
				</View>
			</NativeScreenShell>
		);
	}

	if (estimate) {
		return (
			<EstimateEditor
				client={client}
				initial={estimate}
				onClose={goBack}
			/>
		);
	}

	return (
		<NativeScreenShell onBack={goBack} title="Сметы">
			<View style={styles.center}>
				{message ? (
					<Text style={[styles.error, { color: colors.destructive }]}>
						{message}
					</Text>
				) : (
					<ActivityIndicator color={colors.foreground} />
				)}
			</View>
		</NativeScreenShell>
	);
}

const styles = StyleSheet.create({
	center: {
		alignItems: "center",
		flex: 1,
		justifyContent: "center",
		paddingHorizontal: 24,
	},
	error: { fontSize: 15, textAlign: "center" },
});
