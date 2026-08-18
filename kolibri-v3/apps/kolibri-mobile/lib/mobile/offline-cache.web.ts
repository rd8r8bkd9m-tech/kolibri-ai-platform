const STORAGE_KEY = "kolibri.mobile.offline-cache.v1";
const DEFAULT_TTL_MS = 24 * 60 * 60 * 1_000;

type StoredEntry = {
	value: string;
	createdAt: number;
	ttlMs: number;
};

type CacheMap = Record<string, StoredEntry>;

const readMap = (): CacheMap => {
	if (typeof globalThis.localStorage === "undefined") return {};
	try {
		const raw = globalThis.localStorage.getItem(STORAGE_KEY);
		if (!raw) return {};
		const parsed = JSON.parse(raw) as CacheMap;
		return typeof parsed === "object" && parsed !== null ? parsed : {};
	} catch {
		return {};
	}
};

const writeMap = (map: CacheMap) => {
	if (typeof globalThis.localStorage === "undefined") return;
	try {
		globalThis.localStorage.setItem(STORAGE_KEY, JSON.stringify(map));
	} catch {
		// Private browsing may reject persistent storage.
	}
};

export const writeOfflineCache = async (
	key: string,
	value: unknown,
	ttlMs = DEFAULT_TTL_MS,
) => {
	const map = readMap();
	map[key] = {
		value: JSON.stringify(value),
		createdAt: Date.now(),
		ttlMs,
	};
	writeMap(map);
};

export const readOfflineCache = async <T,>(key: string): Promise<T | null> => {
	const entry = readMap()[key];
	if (!entry) return null;
	if (entry.createdAt + entry.ttlMs < Date.now()) {
		const map = readMap();
		delete map[key];
		writeMap(map);
		return null;
	}
	try {
		return JSON.parse(entry.value) as T;
	} catch {
		return null;
	}
};

export const clearOfflineCache = async () => {
	writeMap({});
};

export const listOfflineCache = async () =>
	Object.entries(readMap()).map(([key, entry]) => ({
		key,
		value: entry.value,
		createdAt: entry.createdAt,
		ttlMs: entry.ttlMs,
	}));
