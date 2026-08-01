import Link from "next/link";

export function PublicBrand() {
	return (
		<Link className="kp-brand" href="/" aria-label="Kolibri AI — на главную">
			<span className="kp-brand-mark" aria-hidden="true">
				<i />
				<i />
				<b />
			</span>
			<span>
				Kolibri<span>AI</span>
			</span>
		</Link>
	);
}
