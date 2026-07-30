import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFile, stat } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const APP_ROOT = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
);
const readSource = (relativePath) =>
  readFile(path.join(APP_ROOT, relativePath), "utf8");

const fileFromPublicUrl = (url) =>
  path.join(APP_ROOT, "public", url.replace(/^\//, ""));

test("the pet roster ships ten original characters with versioned assets", async () => {
  const manifest = JSON.parse(
    await readSource("public/pets/manifest-v1.json"),
  );

  assert.equal(manifest.version, 1);
  assert.equal(manifest.pets.length, 10);
  assert.equal(new Set(manifest.pets.map((pet) => pet.id)).size, 10);
  assert.equal(new Set(manifest.pets.map((pet) => pet.name)).size, 10);
  assert.equal(new Set(manifest.pets.map((pet) => pet.assetSlug)).size, 10);

  for (const pet of manifest.pets) {
    for (const field of [
      "name",
      "personality",
      "role",
      "animation",
      "master",
      "active",
      "thumbnail",
    ]) {
      assert.ok(pet[field], `${pet.id} is missing ${field}`);
    }

    assert.match(pet.master, /\/pets\/masters\/[a-z-]+-v1\.png$/);
    assert.match(pet.active, /\/pets\/active\/[a-z-]+-v1\.webp$/);
    assert.match(pet.thumbnail, /\/pets\/thumbs\/[a-z-]+-v1\.webp$/);

    const [master, active, thumbnail] = await Promise.all([
      stat(fileFromPublicUrl(pet.master)),
      stat(fileFromPublicUrl(pet.active)),
      stat(fileFromPublicUrl(pet.thumbnail)),
    ]);
    assert.ok(master.size > 100_000, `${pet.id} master is unexpectedly small`);
    assert.ok(active.size < 80_000, `${pet.id} active asset is too heavy`);
    assert.ok(thumbnail.size < 12_000, `${pet.id} thumbnail is too heavy`);
  }
});

test("the original Kolibri remains byte-identical in the versioned master", async () => {
  const copiedMaster = await readFile(
    path.join(APP_ROOT, "public/pets/masters/kolibri-v1.png"),
  );

  assert.equal(
    createHash("sha256").update(copiedMaster).digest("hex"),
    "6f30357f75c963e5e4d85b464b10eadb2545d2a6b40aced54861571c4322c3d7",
  );
  assert.equal(copiedMaster.readUInt32BE(16), 1254);
  assert.equal(copiedMaster.readUInt32BE(20), 1254);
  assert.equal(copiedMaster[25], 6, "source PNG must remain RGBA");
});

test("one existing pet component owns selection, movement, hiding and previews", async () => {
  const [pet, settings] = await Promise.all([
    readSource("components/kolibri-shell/kolibri-pet.tsx"),
    readSource("components/kolibri-shell/profile-settings-surface.tsx"),
  ]);

  assert.equal((pet.match(/export function KolibriPet\b/g) ?? []).length, 1);
  assert.equal((pet.match(/export function PetAvatar\b/g) ?? []).length, 1);
  assert.match(pet, /KOLIBRI_PET_SELECTION_KEY\s*=\s*["']kolibri\.ui\.pet-id["']/);
  assert.match(pet, /KOLIBRI_PET_VISIBILITY_KEY\s*=\s*["']kolibri\.ui\.pet-visible["']/);
  assert.match(pet, /setPointerCapture/);
  assert.match(pet, /event\.key === ["']ArrowLeft["']/);
  assert.match(pet, /event\.key === ["']ArrowRight["']/);
  assert.match(pet, /event\.key === ["']ArrowUp["']/);
  assert.match(pet, /event\.key === ["']ArrowDown["']/);
  assert.match(pet, /aria-describedby=\{PET_MOVEMENT_INSTRUCTIONS_ID\}/);
  assert.match(pet, /Клавиши со стрелками перемещают питомца/);
  assert.match(pet, /Shift \+ стрелка перемещает[\s\S]*на большой шаг/);
  assert.match(pet, /const useThumbnail = compact \|\| reducedData/);
  assert.match(pet, /loading=\{useThumbnail \? ["']lazy["'] : ["']eager["']\}/);
  assert.match(pet, /src=\{useThumbnail \? pet\.thumbnail : pet\.asset\}/);
  assert.match(pet, /fetchPriority=\{useThumbnail \? ["']low["'] : ["']high["']\}/);
  assert.match(pet, /matchMedia\(["']\(prefers-reduced-data: reduce\)["']\)/);
  assert.match(pet, /dataConnection\?\.saveData/);

  const reducedDataSync = pet.indexOf("syncReducedData();");
  const firstMountedRender = pet.indexOf("setMounted(true);");
  assert.ok(reducedDataSync >= 0);
  assert.ok(firstMountedRender > reducedDataSync);

  assert.match(pet, /pendingFocusRef\.current = ["']restore["']/);
  assert.match(pet, /pendingFocusRef\.current = ["']collapse["']/);
  assert.match(pet, /restoreButtonRef\.current[\s\S]*collapseButtonRef\.current/);
  assert.match(pet, /target\?\.focus\(\)/);
  assert.match(
    pet,
    /group\/collapse[\s\S]*size-11[\s\S]*<span className=["'][^"']*size-7/,
  );

  assert.match(settings, /role=["']group["']/);
  assert.match(settings, /data-pet-option=\{pet\.id\}/);
  assert.match(settings, /aria-pressed=\{selected\}/);
  assert.match(settings, /\{pet\.personality\}/);
  assert.match(settings, /\{pet\.role\}/);
  assert.match(settings, /Реакция:\s*\{pet\.animation\}/);
  assert.match(
    settings,
    /aria-label=\{`Выбрать питомца \$\{pet\.name\}\. Роль: \$\{pet\.role\}\. Характер: \$\{pet\.personality\}\.[\s\S]*Реакция: \$\{pet\.animation\}\.`\}/,
  );
  assert.doesNotMatch(settings, /\b(Lock|Crown|Gem)\b/);
});

test("each character has a distinct interaction and motion/data reductions", async () => {
  const css = await readSource("app/globals.css");

  for (const petId of [
    "kolibri",
    "lumi",
    "fini",
    "spark",
    "dewdrop",
    "owl",
    "sprout",
    "nimbi",
    "klik",
    "zumi",
  ]) {
    assert.ok(
      css.includes(`data-pet-id="${petId}"`),
      `missing motion contract for ${petId}`,
    );
  }

  for (const animation of [
    "react-wing",
    "react-unfold",
    "react-ears",
    "react-dash",
    "react-gills",
    "react-review",
    "react-grow",
    "react-wave",
    "react-coil",
    "react-buzz",
  ]) {
    assert.ok(css.includes(animation), `missing animation ${animation}`);
  }

  assert.match(css, /@media \(prefers-reduced-motion: reduce\)/);
  assert.match(css, /@media \(prefers-reduced-data: reduce\)/);
  assert.match(
    css,
    /\.kolibri-pet-art__idle,[\s\S]*\.kolibri-pet-art__reaction[\s\S]*animation:\s*none !important/,
  );
});

test("the web pet is a persistent assistant bound to the active Product Chat", async () => {
  const [pet, shell, sidebar, css] = await Promise.all([
    readSource("components/kolibri-shell/kolibri-pet.tsx"),
    readSource("components/kolibri-shell/workspace-shell.tsx"),
    readSource("components/kolibri-shell/workspace-sidebar.tsx"),
    readSource("app/globals.css"),
  ]);

  assert.match(pet, /export function KolibriPetHost/);
  assert.match(shell, /<KolibriPetHost \/>/);
  assert.doesNotMatch(sidebar, /<KolibriPet\b/);
  assert.match(pet, /ComposerPrimitive\.Root/);
  assert.match(pet, /ComposerPrimitive\.Input/);
  assert.match(pet, /ComposerPrimitive\.Send/);
  assert.match(pet, /ComposerPrimitive\.Cancel/);
  assert.match(pet, /useAuiState/);
  assert.match(pet, /state\.thread\.isRunning/);
  assert.match(pet, /(?:state|value)\.composer\.isEmpty/);
  assert.match(pet, /role="dialog"/);
  assert.match(pet, /aria-live="polite"/);
  assert.match(pet, /data-pet-run-state=\{runState\}/);
  assert.match(pet, /"idle" \| "thinking" \| "success" \| "error"/);
  assert.match(pet, /prefers-reduced-motion: reduce/);
  assert.doesNotMatch(pet, /\bfetch\s*\(/);
  assert.doesNotMatch(pet, /setTimeout\([^)]*(fake|mock)|mock response/i);

  for (const state of ["thinking", "success", "error"]) {
    assert.ok(
      css.includes(`data-pet-run-state="${state}"`),
      `missing visual pet state ${state}`,
    );
  }
  assert.match(css, /data-reduced-motion="true"/);
});
