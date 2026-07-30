import { KolibriBird } from "../components/KolibriBird";

function BrandContent() {
  return <>
      <KolibriBird size={38} state="calm" />
      <span>Kolibri<em>AI</em></span>
    </>;
}

export function Brand({ expanded = false, label = "Навигация Kolibri", onActivate, onPreviewEnter, onPreviewLeave }) {
  if (onActivate) {
    return (
      <button
        aria-controls="kolibri-navigation"
        aria-expanded={expanded}
        aria-label={label}
        className="shell-brand is-interactive"
        id="kolibri-navigation-trigger"
        onClick={onActivate}
        onPointerEnter={onPreviewEnter}
        onPointerLeave={onPreviewLeave}
        type="button"
      >
        <BrandContent />
      </button>
    );
  }
  return <a aria-label="Kolibri AI" className="shell-brand" href="/"><BrandContent /></a>;
}
