"use client";

import { useEffect, useState } from "react";
import {
	KOLIBRI_PET_VISIBILITY_EVENT,
	KOLIBRI_PET_VISIBILITY_KEY,
	setKolibriPetVisibility,
} from "@/components/kolibri-shell/kolibri-pet";

export type SidebarPetState = {
	petVisible: boolean;
	togglePet: () => void;
};

export function useSidebarPetState(initial = true): SidebarPetState {
	const [petVisible, setPetVisible] = useState(initial);

	useEffect(() => {
		try {
			const stored = globalThis.localStorage.getItem(
				KOLIBRI_PET_VISIBILITY_KEY,
			);
			if (stored === "false") setPetVisible(false);
			if (stored === "true") setPetVisible(true);
		} catch {
			// A blocked storage API must not affect navigation.
		}

		const syncVisibility = (event: Event) => {
			const detail = (event as CustomEvent<{ visible?: unknown }>).detail;
			if (typeof detail?.visible === "boolean") {
				setPetVisible(detail.visible);
			}
		};

		globalThis.addEventListener(KOLIBRI_PET_VISIBILITY_EVENT, syncVisibility);
		return () =>
			globalThis.removeEventListener(
				KOLIBRI_PET_VISIBILITY_EVENT,
				syncVisibility,
			);
	}, []);

	return {
		petVisible,
		togglePet: () => {
			setPetVisible((current) => {
				const next = !current;
				setKolibriPetVisibility(next);
				return next;
			});
		},
	};
}
