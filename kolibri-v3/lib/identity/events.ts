"use client";

export const KOLIBRI_AUTHENTICATION_REQUIRED_EVENT =
  "kolibri:authentication-required";

export function announceAuthenticationRequired() {
  if (typeof window === "undefined") return;
  window.dispatchEvent(
    new Event(KOLIBRI_AUTHENTICATION_REQUIRED_EVENT),
  );
}
