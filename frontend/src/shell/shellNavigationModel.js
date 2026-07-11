export const initialShellNavigation = Object.freeze({
  mobileOpen: false,
  pinned: false,
  preview: false,
});

export function shellNavigationReducer(state, action) {
  switch (action.type) {
    case "PIN_TOGGLE":
      return { ...state, pinned: !state.pinned, preview: false };
    case "MOBILE_TOGGLE":
      return { ...state, mobileOpen: !state.mobileOpen, preview: false };
    case "PREVIEW_OPEN":
      return state.pinned ? state : { ...state, preview: true };
    case "PREVIEW_CLOSE":
      return { ...state, preview: false };
    case "DISMISS":
      return { ...state, mobileOpen: false, preview: false };
    default:
      return state;
  }
}
