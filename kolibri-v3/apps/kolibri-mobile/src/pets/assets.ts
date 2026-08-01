import type { ImageSourcePropType } from "react-native";
import type { PetId } from "../../../../lib/pets/catalog";

export const NATIVE_PET_ASSETS = {
	kolibri: {
		active: require("../../assets/pets/active/kolibri-v1.webp"),
		thumbnail: require("../../assets/pets/thumbs/kolibri-v1.webp"),
		atlas: require("../../assets/pets/atlases/kolibri-v2.webp"),
	},
	lumi: {
		active: require("../../assets/pets/active/lumi-v1.webp"),
		thumbnail: require("../../assets/pets/thumbs/lumi-v1.webp"),
		atlas: null,
	},
	fini: {
		active: require("../../assets/pets/active/fini-v1.webp"),
		thumbnail: require("../../assets/pets/thumbs/fini-v1.webp"),
		atlas: null,
	},
	spark: {
		active: require("../../assets/pets/active/iskra-v1.webp"),
		thumbnail: require("../../assets/pets/thumbs/iskra-v1.webp"),
		atlas: null,
	},
	dewdrop: {
		active: require("../../assets/pets/active/runi-v1.webp"),
		thumbnail: require("../../assets/pets/thumbs/runi-v1.webp"),
		atlas: null,
	},
	owl: {
		active: require("../../assets/pets/active/buki-v1.webp"),
		thumbnail: require("../../assets/pets/thumbs/buki-v1.webp"),
		atlas: null,
	},
	sprout: {
		active: require("../../assets/pets/active/mohi-v1.webp"),
		thumbnail: require("../../assets/pets/thumbs/mohi-v1.webp"),
		atlas: null,
	},
	nimbi: {
		active: require("../../assets/pets/active/nimbi-v1.webp"),
		thumbnail: require("../../assets/pets/thumbs/nimbi-v1.webp"),
		atlas: null,
	},
	klik: {
		active: require("../../assets/pets/active/klik-v1.webp"),
		thumbnail: require("../../assets/pets/thumbs/klik-v1.webp"),
		atlas: null,
	},
	zumi: {
		active: require("../../assets/pets/active/zumi-v1.webp"),
		thumbnail: require("../../assets/pets/thumbs/zumi-v1.webp"),
		atlas: null,
	},
} as const satisfies Record<
	PetId,
	{
		active: ImageSourcePropType;
		thumbnail: ImageSourcePropType;
		atlas: ImageSourcePropType | null;
	}
>;

export type NativePetId = PetId;

export type NativePetAssetSet = {
	active: ImageSourcePropType;
	thumbnail: ImageSourcePropType;
	atlas: ImageSourcePropType | null;
};
