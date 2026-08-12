"use client";

import { useEffect, useRef, useState } from "react";
import { WebPetSprite } from "@/components/kolibri-shell/pet/pet-sprite";
import type { PetVisualState } from "@/lib/pets/motion";

const KOLIBRI_ARTWORK = {
	id: "kolibri",
	active: "/pets/active/kolibri-v1.webp",
	atlas: "/pets/atlases/kolibri-v2.webp",
	thumbnail: "/pets/thumbs/kolibri-v1.webp",
};

const KOLIBRI_MOODS = [
	"Готов помочь",
	"Слушаю задачу",
	"Уже лечу",
	"Всё под контролем",
] as const;

export function LandingPet({
	className = "",
	interactive = false,
	width = 30,
}: {
	className?: string;
	interactive?: boolean;
	width?: number;
}) {
	const [reducedMotion, setReducedMotion] = useState(false);
	const [state, setState] = useState<PetVisualState>("idle");
	const [mood, setMood] = useState<string | null>(null);
	const moodCursor = useRef(0);
	const resetTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

	useEffect(() => {
		const query = window.matchMedia("(prefers-reduced-motion: reduce)");
		const sync = () => setReducedMotion(query.matches);
		sync();
		query.addEventListener("change", sync);
		return () => query.removeEventListener("change", sync);
	}, []);

	useEffect(() => () => {
		if (resetTimer.current !== null) clearTimeout(resetTimer.current);
	}, []);

	const react = (event?: { preventDefault?: () => void; stopPropagation?: () => void }) => {
		if (!interactive) return;
		event?.preventDefault?.();
		event?.stopPropagation?.();
		setMood(KOLIBRI_MOODS[moodCursor.current % KOLIBRI_MOODS.length]);
		moodCursor.current += 1;
		setState("greeting");
		if (resetTimer.current !== null) clearTimeout(resetTimer.current);
		resetTimer.current = globalThis.setTimeout(() => {
			setState("idle");
			setMood(null);
		}, 900);
	};

	return (
		<span
			className={`klp-pet ${className}`.trim()}
			role={interactive ? "button" : undefined}
			tabIndex={interactive ? 0 : undefined}
			aria-label={interactive ? "Коли — помахать крыльями" : undefined}
			onClick={react}
			onKeyDown={(event) => {
				if (!interactive) return;
				if (event.key === "Enter" || event.key === " ") {
					event.preventDefault();
					react(event);
				}
			}}
		>
			<WebPetSprite
				pet={KOLIBRI_ARTWORK}
				reducedMotion={reducedMotion}
				state={state}
				width={width}
			/>
			{mood ? <span className="klp-pet-mood">{mood}</span> : null}
		</span>
	);
}
