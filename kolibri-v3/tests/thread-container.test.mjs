import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const APP_ROOT = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
);

const readSource = (relativePath) =>
  readFile(path.join(APP_ROOT, relativePath), "utf8");

test("the Kolibri chat is composed from the streaming assistant-ui thread primitives", async () => {
  const [thread, attachment] = await Promise.all([
    readSource("components/assistant-ui/thread.tsx"),
    readSource("components/assistant-ui/attachment.tsx"),
  ]);

  for (const primitive of [
    "ThreadPrimitive.Root",
    "ThreadPrimitive.Viewport",
    "ThreadPrimitive.Messages",
    "ThreadPrimitive.ViewportFooter",
    "ThreadPrimitive.ScrollToBottom",
    "ComposerPrimitive.Root",
    "ComposerPrimitive.Input",
    "ComposerPrimitive.AttachmentDropzone",
    "ComposerPrimitive.AddAttachment",
    "ComposerPrimitive.Send",
    "ComposerPrimitive.Cancel",
  ]) {
    assert.ok(thread.includes(primitive), `missing ${primitive}`);
  }
  assert.ok(
    attachment.includes("ComposerPrimitive.Attachments"),
    "missing ComposerPrimitive.Attachments",
  );

  assert.match(thread, /\bautoScroll=\{true\}/);
  assert.match(thread, /\bscrollToBottomOnInitialize=\{true\}/);
  assert.match(thread, /\bscrollToBottomOnRunStart=\{true\}/);
  assert.match(thread, /\bscrollToBottomOnThreadSwitch=\{true\}/);
  assert.match(
    thread,
    /ComposerPrimitive\.AttachmentDropzone[\s\S]{0,100}\bdisabled=\{attachmentsDisabled\}/,
  );
  assert.match(thread, /\baria-busy=\{isRunning\}/);
  assert.match(thread, /\brole=["']status["']/);
  assert.match(thread, /\brole=["']log["']/);
  assert.match(thread, /\baria-live=["']polite["']/);
  assert.match(thread, /\baria-relevant=["']additions["']/);
  assert.match(thread, /\bcapabilities\.attachments\b/);
  assert.match(thread, /\bcomposer\.attachmentAddError\b/);
  assert.doesNotMatch(thread, /<textarea\b/i);
  assert.doesNotMatch(thread, /\bautoSend\b/);
  assert.doesNotMatch(thread, /\bmethod=["']replace["']/);
});

test("attachment controls expose localized accessible names and states", async () => {
  const attachment = await readSource(
    "components/assistant-ui/attachment.tsx",
  );

  for (const text of [
    "Предпросмотр вложения",
    "Предпросмотр изображения",
    "Изображение",
    "Документ",
    "Файл",
    "загрузка не удалась",
    "загружается",
    "Удалить файл",
    "Добавить вложение",
  ]) {
    assert.ok(attachment.includes(text), `missing accessible text: ${text}`);
  }
});
