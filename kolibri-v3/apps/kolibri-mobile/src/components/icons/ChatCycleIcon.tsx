import Svg, { Path } from "react-native-svg";

import { useTheme } from "@/hooks/use-theme";

export function ChatCycleIcon({
	color,
	size = 24,
}: {
	color?: string;
	size?: number;
}) {
	const { colors } = useTheme();
	const stroke = color ?? colors.foreground;
	return (
		<Svg fill="none" height={size} viewBox="0 0 24 24" width={size}>
			<Path
				d="M12 3a9 9 0 0 1 8.86 7.44"
				stroke={stroke}
				strokeLinecap="round"
				strokeWidth={2.2}
			/>
			<Path
				d="M19.79 16.5a9 9 0 0 1-9.35 4.35"
				stroke={stroke}
				strokeLinecap="round"
				strokeWidth={2.2}
			/>
			<Path
				d="M5.11 6.21a9 9 0 0 0-.9 10.29"
				stroke={stroke}
				strokeLinecap="round"
				strokeWidth={2.2}
			/>
			<Path
				d="M4.21 16.5l1.5 2.5 2.7-1.6"
				stroke={stroke}
				strokeLinecap="round"
				strokeLinejoin="round"
				strokeWidth={2.2}
			/>
		</Svg>
	);
}
