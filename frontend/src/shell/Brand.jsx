import { KolibriBird } from "../components/KolibriBird";

export function Brand() {
  return (
    <a aria-label="Kolibri AI" className="shell-brand" href="/">
      <KolibriBird size={38} state="calm" />
      <span>Kolibri<em>AI</em></span>
    </a>
  );
}
