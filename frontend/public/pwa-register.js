const registerServiceWorker = () => {
  navigator.serviceWorker.register("/service-worker.js", { scope: "/" }).catch((error) => {
    console.warn("Service worker registration failed:", error);
  });
};

if (document.readyState === "complete") {
  registerServiceWorker();
} else {
  window.addEventListener("load", registerServiceWorker, { once: true });
}
