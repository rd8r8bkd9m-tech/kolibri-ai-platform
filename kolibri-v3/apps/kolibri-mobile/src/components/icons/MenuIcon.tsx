import Svg, { Line } from "react-native-svg";

import { useTheme } from "@/hooks/use-theme";

export function MenuIcon({
	color,
	size = 26,
}: {
	color?: string;
	size?: number;
}) {
	const { colors } = useTheme();
	const stroke = color ?? colors.foreground;
	return (
		<Svg fill="none" height={size} viewBox="0 0 26 24" width={size}>
			<Line
				stroke={stroke}
				strokeLinecap="round"
				strokeWidth={2}
				x1="0"
				x2="26"
				y1="6"
				y2="6"
			/>
			<Line
				stroke={stroke}
				strokeLinecap="round"
				strokeWidth={2}
				x1="0"
				x2="17"
				y1="18"
				y2="18"
			/>
		</Svg>
	);
}
