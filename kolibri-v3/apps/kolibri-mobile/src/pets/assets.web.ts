import type { ImageSourcePropType } from "react-native";

import { PET_CATALOG, type PetId } from "../../../../lib/pets/catalog";

/**
 * Expo web runs behind the unified 3103 gateway. Web artwork is therefore
 * served by the canonical V3 public asset owner instead of a Metro-generated
 * development URL. Native builds keep using the static registry from
 * assets.ts so iOS/Android remain fully bundled and offline.
 */
export const NATIVE_PET_ASSETS = Object.fromEntries(
	PET_CATALOG.map((pet) => [
		pet.id,
		{
			active: { uri: `/pets/active/${pet.assetSlug}-v1.webp` },
			atlas: pet.motionAssetVersion
				? {
						uri: `/pets/atlases/${pet.assetSlug}-${pet.motionAssetVersion}.webp`,
					}
				: null,
			thumbnail: { uri: `/pets/thumbs/${pet.assetSlug}-v1.webp` },
		},
	]),
) as Record<
	PetId,
	{
		active: ImageSourcePropType;
		atlas: ImageSourcePropType | null;
		thumbnail: ImageSourcePropType;
	}
>;

export type NativePetId = PetId;

export type NativePetAssetSet = {
	active: ImageSourcePropType;
	atlas: ImageSourcePropType | null;
	thumbnail: ImageSourcePropType;
};
