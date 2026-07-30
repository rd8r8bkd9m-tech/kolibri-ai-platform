export const THREAD_LONG_PRESS_DURATION_MS = 520;
export const THREAD_LONG_PRESS_MOVE_TOLERANCE_PX = 8;
export const THREAD_LONG_PRESS_CLICK_SUPPRESSION_MS = 1_500;

export function canStartThreadLongPress({
  isDraft,
  pointerType,
}: {
  isDraft: boolean;
  pointerType: string;
}) {
  return (
    !isDraft && (pointerType === "touch" || pointerType === "pen")
  );
}

export function shouldCloseThreadDrawerForClick({
  isThreadTrigger,
  longPressConsumed,
}: {
  isThreadTrigger: boolean;
  longPressConsumed: boolean;
}) {
  return isThreadTrigger && !longPressConsumed;
}

export function shouldIgnoreThreadMenuCloseRequest({
  open,
  longPressClickPending,
}: {
  open: boolean;
  longPressClickPending: boolean;
}) {
  return !open && longPressClickPending;
}
