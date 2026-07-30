import type { ImageSourcePropType } from "react-native";

export type NativePetId =
  | "kolibri"
  | "lumi"
  | "fini"
  | "spark"
  | "dewdrop"
  | "owl"
  | "sprout"
  | "nimbi"
  | "klik"
  | "zumi";

export type NativePetDefinition = {
  id: NativePetId;
  name: string;
  role: string;
  personality: string;
  accent: string;
  active: ImageSourcePropType;
  thumbnail: ImageSourcePropType;
};

/**
 * Metro requires static image paths. Keep this release registry explicit so a
 * server response can select only artwork bundled and reviewed with the app.
 */
export const NATIVE_PETS: readonly NativePetDefinition[] = [
  {
    id: "kolibri",
    name: "Коли",
    role: "Универсал",
    personality: "Энергичный и внимательный",
    accent: "#24c7d4",
    active: require("../../assets/pets/active/kolibri-v1.webp"),
    thumbnail: require("../../assets/pets/thumbs/kolibri-v1.webp"),
  },
  {
    id: "lumi",
    name: "Луми",
    role: "Фокус",
    personality: "Мягкая и вдумчивая",
    accent: "#b6a1f2",
    active: require("../../assets/pets/active/lumi-v1.webp"),
    thumbnail: require("../../assets/pets/thumbs/lumi-v1.webp"),
  },
  {
    id: "fini",
    name: "Фини",
    role: "Разведчик",
    personality: "Любопытный и находчивый",
    accent: "#e8b782",
    active: require("../../assets/pets/active/fini-v1.webp"),
    thumbnail: require("../../assets/pets/thumbs/fini-v1.webp"),
  },
  {
    id: "spark",
    name: "Искра",
    role: "Ускоритель",
    personality: "Смелая и стремительная",
    accent: "#ff8b3d",
    active: require("../../assets/pets/active/iskra-v1.webp"),
    thumbnail: require("../../assets/pets/thumbs/iskra-v1.webp"),
  },
  {
    id: "dewdrop",
    name: "Руни",
    role: "Поддержка",
    personality: "Терпеливый и добрый",
    accent: "#70d9de",
    active: require("../../assets/pets/active/runi-v1.webp"),
    thumbnail: require("../../assets/pets/thumbs/runi-v1.webp"),
  },
  {
    id: "owl",
    name: "Буки",
    role: "Ревьюер",
    personality: "Точный и рассудительный",
    accent: "#5b5bd6",
    active: require("../../assets/pets/active/buki-v1.webp"),
    thumbnail: require("../../assets/pets/thumbs/buki-v1.webp"),
  },
  {
    id: "sprout",
    name: "Мохи",
    role: "Строитель",
    personality: "Надёжный и созидательный",
    accent: "#79c99a",
    active: require("../../assets/pets/active/mohi-v1.webp"),
    thumbnail: require("../../assets/pets/thumbs/mohi-v1.webp"),
  },
  {
    id: "nimbi",
    name: "Нимби",
    role: "Идейник",
    personality: "Мечтательный и изобретательный",
    accent: "#72d8f2",
    active: require("../../assets/pets/active/nimbi-v1.webp"),
    thumbnail: require("../../assets/pets/thumbs/nimbi-v1.webp"),
  },
  {
    id: "klik",
    name: "Клик",
    role: "Исполнитель",
    personality: "Собранный и технический",
    accent: "#3a9fa8",
    active: require("../../assets/pets/active/klik-v1.webp"),
    thumbnail: require("../../assets/pets/thumbs/klik-v1.webp"),
  },
  {
    id: "zumi",
    name: "Зуми",
    role: "Мотиватор",
    personality: "Радостный и отзывчивый",
    accent: "#f2c84b",
    active: require("../../assets/pets/active/zumi-v1.webp"),
    thumbnail: require("../../assets/pets/thumbs/zumi-v1.webp"),
  },
] as const;

export const DEFAULT_NATIVE_PET = NATIVE_PETS[0];
