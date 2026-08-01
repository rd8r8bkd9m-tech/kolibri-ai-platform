"use client";

import { useEffect, useState } from "react";
import {
	PET_ATLAS_LAYOUT,
	PET_MOTION_CLIPS,
	getPetFrameAtElapsedMs,
	type PetVisualState,
} from "@/lib/pets/motion";

type WebPetArtwork = {
	active: string;
	atlas: string | null;
	id: string;
	thumbnail: string;
};

export function WebPetSprite({
	pet,
	reducedData = false,
	reducedMotion = false,
	state,
	width,
}: {
	pet: WebPetArtwork;
	reducedData?: boolean;
	reducedMotion?: boolean;
	state: PetVisualState;
	width: number;
}) {
	const clip = PET_MOTION_CLIPS[state];
	const key = `${pet.id}:${state}:${reducedMotion ? "reduced" : "full"}`;
	if (!pet.atlas || reducedData) {
		return (
			<img
				alt=""
				className="size-full object-contain"
				decoding="async"
				draggable={false}
				fetchPriority={reducedData ? "low" : "high"}
				height={reducedData ? 144 : 512}
				loading={reducedData ? "lazy" : "eager"}
				src={reducedData ? pet.thumbnail : pet.active}
				width={reducedData ? 144 : 512}
			/>
		);
	}
	return (
		<WebPetSpriteFrame
			key={key}
			atlas={pet.atlas}
			clip={clip}
			reducedMotion={reducedMotion}
			width={width}
		/>
	);
}

function WebPetSpriteFrame({
	atlas,
	clip,
	reducedMotion,
	width,
}: {
	atlas: string;
	clip: (typeof PET_MOTION_CLIPS)[PetVisualState];
	reducedMotion: boolean;
	width: number;
}) {
	const [frame, setFrame] = useState(() =>
		getPetFrameAtElapsedMs(clip, 0, reducedMotion),
	);
	const frameHeight =
		width * (PET_ATLAS_LAYOUT.cellHeight / PET_ATLAS_LAYOUT.cellWidth);

	useEffect(() => {
		if (reducedMotion) return;
		let active = true;
		let timer: ReturnType<typeof setTimeout> | undefined;
		const startedAt = Date.now();
		const scheduleNextFrame = () => {
			if (!active) return;
			const nextFrame = getPetFrameAtElapsedMs(clip, Date.now() - startedAt);
			setFrame(nextFrame);
			if (!clip.loop && nextFrame === clip.frameDurationsMs.length - 1) return;
			timer = setTimeout(
				scheduleNextFrame,
				clip.frameDurationsMs[nextFrame] ?? 120,
			);
		};
		timer = setTimeout(scheduleNextFrame, clip.frameDurationsMs[0] ?? 120);
		return () => {
			active = false;
			if (timer !== undefined) clearTimeout(timer);
		};
	}, [clip, reducedMotion]);

	return (
		<span
			aria-hidden="true"
			className="relative block overflow-hidden"
			style={{ height: frameHeight, width }}
		>
			<img
				alt=""
				className="pointer-events-none absolute max-w-none select-none"
				decoding="async"
				draggable={false}
				height={frameHeight * PET_ATLAS_LAYOUT.rows}
				src={atlas}
				style={{
					height: frameHeight * PET_ATLAS_LAYOUT.rows,
					left: -frame * width,
					top: -clip.row * frameHeight,
					width: width * PET_ATLAS_LAYOUT.columns,
				}}
				width={width * PET_ATLAS_LAYOUT.columns}
			/>
		</span>
	);
}
