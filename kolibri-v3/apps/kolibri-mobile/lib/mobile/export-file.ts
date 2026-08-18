import { EncodingType, File, Paths } from "expo-file-system";
import * as Sharing from "expo-sharing";
import { Platform } from "react-native";

import type { EstimateExportResult } from "@/src/verticals/construction-estimates/export";

const webDownload = (result: EstimateExportResult) => {
	const url = URL.createObjectURL(result.blob);
	const anchor = document.createElement("a");
	anchor.href = url;
	anchor.download = result.filename;
	document.body.appendChild(anchor);
	anchor.click();
	anchor.remove();
	URL.revokeObjectURL(url);
};

const nativeShare = async (result: EstimateExportResult) => {
	const dataUrl = await new Promise<string>((resolve, reject) => {
		const reader = new FileReader();
		reader.onload = () => resolve(reader.result as string);
		reader.onerror = () => reject(reader.error);
		reader.readAsDataURL(result.blob);
	});
	const base64 = dataUrl.slice(dataUrl.indexOf(",") + 1);
	const file = new File(Paths.cache, result.filename);
	file.write(base64, {
		encoding: EncodingType.Base64,
	});
	await Sharing.shareAsync(file.uri, {
		mimeType: result.mimeType,
		dialogTitle: `Поделиться: ${result.filename}`,
	});
};

export const exportAndShare = async (result: EstimateExportResult) => {
	if (Platform.OS === "web") {
		webDownload(result);
		return;
	}
	await nativeShare(result);
};
