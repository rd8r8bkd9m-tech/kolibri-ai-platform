import * as SecureStore from "expo-secure-store";
import { Platform } from "react-native";

import {
  DEFAULT_NATIVE_PET,
  NATIVE_PETS,
  type NativePetDefinition,
  type NativePetId,
} from "@/src/pets/registry";

export const NATIVE_PET_SELECTION_KEY = "kolibri.mobile.pet-id.v1";

export function isNativePetId(value: unknown): value is NativePetId {
  return (
    typeof value === "string" &&
    NATIVE_PETS.some((candidate) => candidate.id === value)
  );
}

export function getNativePet(id: NativePetId): NativePetDefinition {
  return (
    NATIVE_PETS.find((candidate) => candidate.id === id) ??
    DEFAULT_NATIVE_PET
  );
}

export async function readNativePetId(): Promise<NativePetId> {
  try {
    const stored =
      Platform.OS === "web"
        ? globalThis.localStorage?.getItem(NATIVE_PET_SELECTION_KEY)
        : await SecureStore.getItemAsync(NATIVE_PET_SELECTION_KEY);
    return isNativePetId(stored) ? stored : DEFAULT_NATIVE_PET.id;
  } catch {
    return DEFAULT_NATIVE_PET.id;
  }
}

export async function persistNativePetId(
  id: NativePetId,
): Promise<boolean> {
  if (!isNativePetId(id)) return false;
  try {
    if (Platform.OS === "web") {
      globalThis.localStorage?.setItem(NATIVE_PET_SELECTION_KEY, id);
    } else {
      await SecureStore.setItemAsync(NATIVE_PET_SELECTION_KEY, id, {
        keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
      });
    }
    return true;
  } catch {
    return false;
  }
}
