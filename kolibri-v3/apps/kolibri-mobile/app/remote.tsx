import { useRouter } from "expo-router";

import { NativeScreenShell } from "@/components/shell/native-screen-shell";
import { SurfaceBoundary } from "@/components/shell/surface-boundary";

export default function RemoteScreen() {
	const router = useRouter();
	return (
		<NativeScreenShell
			onBack={() => router.replace("/app?client=mobile")}
			title="Удаленно"
		>
			<SurfaceBoundary
				body="Подключения к внешним источникам появятся, когда сервер активирует интеграции."
				icon="bubble"
				note="Сортировка и настройки соединений станут доступны вместе с первой реальной интеграцией."
				title="Внешние источники не подключены"
			/>
		</NativeScreenShell>
	);
}
