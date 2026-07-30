import assert from "node:assert/strict";
import test from "node:test";

import {
  canStartThreadLongPress,
  shouldIgnoreThreadMenuCloseRequest,
  shouldCloseThreadDrawerForClick,
  THREAD_LONG_PRESS_CLICK_SUPPRESSION_MS,
  THREAD_LONG_PRESS_DURATION_MS,
} from "../lib/mobile-thread-navigation.ts";

test("a normal thread tap still selects the thread and closes the drawer", () => {
  assert.equal(
    shouldCloseThreadDrawerForClick({
      isThreadTrigger: true,
      longPressConsumed: false,
    }),
    true,
  );
});

test("a consumed long press leaves the drawer open for the thread action menu", () => {
  assert.equal(THREAD_LONG_PRESS_DURATION_MS, 520);
  assert.equal(
    canStartThreadLongPress({
      isDraft: false,
      pointerType: "touch",
    }),
    true,
  );
  assert.equal(
    shouldCloseThreadDrawerForClick({
      isThreadTrigger: true,
      longPressConsumed: true,
    }),
    false,
  );
});

test("draft threads never consume a long press and retain ordinary tap navigation", () => {
  assert.equal(
    canStartThreadLongPress({
      isDraft: true,
      pointerType: "touch",
    }),
    false,
  );
  assert.equal(
    shouldCloseThreadDrawerForClick({
      isThreadTrigger: true,
      longPressConsumed: false,
    }),
    true,
  );
});

test("mouse presses do not enter the touch long-press state", () => {
  assert.equal(
    canStartThreadLongPress({
      isDraft: false,
      pointerType: "mouse",
    }),
    false,
  );
});

test("the menu ignores the touch-end close request until the synthetic click is consumed", () => {
  assert.equal(THREAD_LONG_PRESS_CLICK_SUPPRESSION_MS, 1_500);
  assert.equal(
    shouldIgnoreThreadMenuCloseRequest({
      open: false,
      longPressClickPending: true,
    }),
    true,
  );
  assert.equal(
    shouldIgnoreThreadMenuCloseRequest({
      open: false,
      longPressClickPending: false,
    }),
    false,
  );
  assert.equal(
    shouldIgnoreThreadMenuCloseRequest({
      open: true,
      longPressClickPending: true,
    }),
    false,
  );
});
