import {
	openDatabaseAsync,
	type SQLiteDatabase,
} from "expo-sqlite";

const DATABASE_NAME = "kolibri-mobile-cache.db";
const DEFAULT_TTL_MS = 24 * 60 * 60 * 1_000;

type CacheEntry = {
	key: string;
	value: string;
	createdAt: number;
	ttlMs: number;
};

let databasePromise: Promise<SQLiteDatabase> | null = null;

const database = () => {
	if (!databasePromise) {
		databasePromise = openDatabaseAsync(DATABASE_NAME).then(async (db) => {
			await db.execAsync(`
				PRAGMA journal_mode = WAL;
				CREATE TABLE IF NOT EXISTS offline_cache (
					key TEXT PRIMARY KEY NOT NULL,
					value TEXT NOT NULL,
					created_at INTEGER NOT NULL,
					ttl_ms INTEGER NOT NULL
				);
			`);
			return db;
		});
	}
	return databasePromise;
};

export const writeOfflineCache = async (
	key: string,
	value: unknown,
	ttlMs = DEFAULT_TTL_MS,
) => {
	const db = await database();
	const createdAt = Date.now();
	await db.runAsync(
		`
			INSERT INTO offline_cache (key, value, created_at, ttl_ms)
			VALUES (?, ?, ?, ?)
			ON CONFLICT(key) DO UPDATE SET
				value = excluded.value,
				created_at = excluded.created_at,
				ttl_ms = excluded.ttl_ms
		`,
		key,
		JSON.stringify(value),
		createdAt,
		ttlMs,
	);
};

export const readOfflineCache = async <T,>(key: string): Promise<T | null> => {
	const db = await database();
	const row = await db.getFirstAsync<{
		value: string;
		created_at: number;
		ttl_ms: number;
	}>(
		"SELECT value, created_at, ttl_ms FROM offline_cache WHERE key = ?",
		key,
	);
	if (!row) return null;
	const expiresAt = Number(row.created_at) + Number(row.ttl_ms);
	if (expiresAt < Date.now()) {
		await db.runAsync("DELETE FROM offline_cache WHERE key = ?", key);
		return null;
	}
	try {
		return JSON.parse(row.value) as T;
	} catch {
		return null;
	}
};

export const clearOfflineCache = async () => {
	const db = await database();
	await db.runAsync("DELETE FROM offline_cache");
};

export const listOfflineCache = async (): Promise<CacheEntry[]> => {
	const db = await database();
	const rows = await db.getAllAsync<{
		key: string;
		value: string;
		created_at: number;
		ttl_ms: number;
	}>("SELECT key, value, created_at, ttl_ms FROM offline_cache ORDER BY created_at DESC");
	return rows.map((row) => ({
		key: row.key,
		value: row.value,
		createdAt: Number(row.created_at),
		ttlMs: Number(row.ttl_ms),
	}));
};
