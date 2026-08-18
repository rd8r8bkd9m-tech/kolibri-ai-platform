import { useLocalSearchParams, useRouter } from "expo-router";
import { useEffect, useState } from "react";
import {
	ActivityIndicator,
	Platform,
	StyleSheet,
	Text,
	View,
} from "react-native";

import { useTheme } from "@/hooks/use-theme";
import { useMobileSession } from "@/src/auth/mobile-session";

export default function MagicLinkVerifyScreen() {
	const router = useRouter();
	const { colors } = useTheme();
	const session = useMobileSession();
	const { email, token } = useLocalSearchParams<{
		email?: string;
		token?: string;
	}>();
	const [error, setError] = useState<string | null>(null);
	const missing = !email || !token;

	useEffect(() => {
		if (missing || !email || !token) return;
		let active = true;
		void session
			.verifyMagicLink(email, token)
			.then(() => {
				if (!active) return;
				if (Platform.OS === "web") {
					globalThis.location.replace("/app?client=mobile");
				} else {
					router.replace("/app?client=mobile");
				}
			})
			.catch((reason: unknown) => {
				if (active) {
					setError(
						reason instanceof Error
							? reason.message
							: "Не удалось войти по ссылке.",
					);
				}
			});
		return () => {
			active = false;
		};
	}, [email, missing, router, session, token]);

	return (
		<View style={[styles.root, { backgroundColor: colors.background }]}>
			{missing ? (
				<Text style={[styles.error, { color: colors.destructive }]}>
					Недействительная ссылка для входа.
				</Text>
			) : error ? (
				<Text style={[styles.error, { color: colors.destructive }]}>{error}</Text>
			) : (
				<ActivityIndicator color={colors.foreground} />
			)}
		</View>
	);
}

const styles = StyleSheet.create({
	root: {
		alignItems: "center",
		flex: 1,
		justifyContent: "center",
		padding: 24,
	},
	error: { fontSize: 16, textAlign: "center" },
});
