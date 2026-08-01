import { useEffect, useState } from "react";
import { Image, StyleSheet, View } from "react-native";
import { useReducedMotion } from "react-native-reanimated";

import type { NativePetDefinition } from "@/src/pets/registry";
import {
	PET_ATLAS_LAYOUT,
	PET_MOTION_CLIPS,
	getPetFrameAtElapsedMs,
	type PetVisualState,
} from "@/src/pets/motion";

type PetSpriteProps = {
	pet: NativePetDefinition;
	state: PetVisualState;
	width?: number;
	reducedMotion?: boolean;
	testID?: string;
};

export function PetSprite({
	pet,
	state,
	width = 56,
	reducedMotion,
	testID,
}: PetSpriteProps) {
	const systemReducedMotion = useReducedMotion();
	const shouldReduceMotion = reducedMotion ?? systemReducedMotion;
	const clip = PET_MOTION_CLIPS[state];
	const animationKey = `${pet.id}:${state}:${shouldReduceMotion ? "reduced" : "full"}`;

	return (
		<PetSpriteFrame
			key={animationKey}
			clip={clip}
			pet={pet}
			reducedMotion={shouldReduceMotion}
			testID={testID}
			width={width}
		/>
	);
}

function PetSpriteFrame({
	clip,
	pet,
	reducedMotion,
	testID,
	width,
}: {
	clip: (typeof PET_MOTION_CLIPS)[PetVisualState];
	pet: NativePetDefinition;
	reducedMotion: boolean;
	testID?: string;
	width: number;
}) {
	const [frame, setFrame] = useState(() =>
		getPetFrameAtElapsedMs(clip, 0, reducedMotion),
	);
	const frameHeight =
		width * (PET_ATLAS_LAYOUT.cellHeight / PET_ATLAS_LAYOUT.cellWidth);

	useEffect(() => {
		if (!pet.atlas || reducedMotion) return;

		let active = true;
		let timer: ReturnType<typeof setTimeout> | undefined;
		const startedAt = Date.now();

		const scheduleNextFrame = () => {
			if (!active) return;
			const elapsedMs = Date.now() - startedAt;
			const nextFrame = getPetFrameAtElapsedMs(clip, elapsedMs);
			setFrame(nextFrame);

			if (!clip.loop && nextFrame === clip.frameDurationsMs.length - 1) {
				return;
			}
			const currentFrameDuration = clip.frameDurationsMs[nextFrame] ?? 120;
			timer = setTimeout(scheduleNextFrame, currentFrameDuration);
		};

		timer = setTimeout(scheduleNextFrame, clip.frameDurationsMs[0] ?? 120);
		return () => {
			active = false;
			if (timer !== undefined) clearTimeout(timer);
		};
	}, [clip, pet.atlas, reducedMotion]);

	if (!pet.atlas) {
		return (
			<Image
				accessibilityElementsHidden
				importantForAccessibility="no-hide-descendants"
				resizeMode="contain"
				source={pet.active}
				style={{ height: frameHeight, width }}
				testID={testID}
			/>
		);
	}

	return (
		<View
			accessibilityElementsHidden
			importantForAccessibility="no-hide-descendants"
			style={[styles.viewport, { height: frameHeight, width }]}
			testID={testID}
		>
			<Image
				resizeMode="stretch"
				source={pet.atlas}
				style={[
					styles.atlas,
					{
						height: frameHeight * PET_ATLAS_LAYOUT.rows,
						left: -frame * width,
						top: -clip.row * frameHeight,
						width: width * PET_ATLAS_LAYOUT.columns,
					},
				]}
			/>
		</View>
	);
}

const styles = StyleSheet.create({
	viewport: {
		overflow: "hidden",
	},
	atlas: {
		position: "absolute",
	},
});
