export type SelectableCatalogModel = {
	readonly profile: string;
	readonly id: string;
	readonly isDefault: boolean;
};

export type SavedModelSelection = {
	readonly preferredAgentProfile?: string | null;
	readonly preferredModel?: string | null;
};

export function catalogModelSelectionId(
	model: Pick<SelectableCatalogModel, "profile" | "id">,
) {
	return `${model.profile}:${model.id}`;
}

export function effectiveModelSelectionId(
	models: readonly SelectableCatalogModel[],
	selection: SavedModelSelection | null,
) {
	const profile = selection?.preferredAgentProfile;
	const automatic = models.find((model) => model.profile === "auto");
	if (!profile) {
		return automatic ? catalogModelSelectionId(automatic) : undefined;
	}

	const resolved =
		models.find(
			(model) =>
				model.profile === profile &&
				model.id === selection?.preferredModel,
		) ??
		models.find((model) => model.profile === profile && model.isDefault) ??
		models.find((model) => model.profile === profile) ??
		(profile === "auto" ? automatic : undefined);

	return resolved ? catalogModelSelectionId(resolved) : undefined;
}
