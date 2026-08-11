export const THREAD_ROOT_CSS_VARS: Record<string, string> = {
	"--thread-max-width": "46rem",
	// ChatGPT-style composer surface. The Tailwind variable utilities are not
	// reliably emitted for this project, so globals.css applies these vars to
	// the composer shell directly.
	"--composer-bg": "var(--secondary)",
	"--composer-radius": "1.5rem",
	"--composer-padding": "8px",
};
