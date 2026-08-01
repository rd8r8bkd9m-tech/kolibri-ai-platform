import {
	NATIVE_PET_ASSETS,
	type NativePetAssetSet,
	type NativePetId,
} from "@/src/pets/assets";
import { PET_CATALOG, type PetIdentity } from "../../../../lib/pets/catalog";

export type { NativePetId } from "@/src/pets/assets";

export type NativePetDefinition = {
	id: NativePetId;
	active: NativePetAssetSet["active"];
	thumbnail: NativePetAssetSet["thumbnail"];
	atlas: NativePetAssetSet["atlas"];
} & PetIdentity;

/**
 * Metro requires static image paths. Keep this release registry explicit so a
 * server response can select only artwork bundled and reviewed with the app.
 */
export const NATIVE_PETS: readonly NativePetDefinition[] = PET_CATALOG.map(
	(pet) => ({ ...pet, ...NATIVE_PET_ASSETS[pet.id] }),
);

export const DEFAULT_NATIVE_PET = NATIVE_PETS[0];
