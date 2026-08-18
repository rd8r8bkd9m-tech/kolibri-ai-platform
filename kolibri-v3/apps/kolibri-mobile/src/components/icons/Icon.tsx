import type { IconName } from "@/components/ui/icon-mappings";
import {
	Archive,
	AudioWaveform,
	BookOpen,
	Check,
	ChevronDown,
	ChevronLeft,
	ChevronRight,
	ChevronUp,
	CircleCheck,
	Copy,
	Ellipsis,
	FileText,
	Folder,
	Globe,
	GraduationCap,
	History,
	Image,
	Info,
	Library,
	LogOut,
	MessageCircle,
	Mic,
	Minus,
	Monitor,
	PenLine,
	PenTool,
	Pin,
	PinOff,
	Plus,
	RotateCw,
	Search,
	Send,
	Settings,
	Share,
	ShieldCheck,
	SlidersHorizontal,
	SmilePlus,
	Sparkles,
	Square,
	SquarePen,
	SunMoon,
	Trash2,
	User,
	X,
	HelpCircle,
	type LucideIcon,
} from "lucide-react-native";

const ICONS: Partial<Record<IconName, LucideIcon>> = {
	compose: SquarePen,
	bubble: MessageCircle,
	plus: Plus,
	send: Send,
	stop: Square,
	copy: Copy,
	check: Check,
	reload: RotateCw,
	"chevron-left": ChevronLeft,
	"chevron-right": ChevronRight,
	folder: Folder,
	library: Library,
	settings: Settings,
	search: Search,
	archive: Archive,
	pin: Pin,
	document: FileText,
	person: User,
	appearance: SunMoon,
	agent: Sparkles,
	model: SlidersHorizontal,
	shield: ShieldCheck,
	info: Info,
	"chevron-down": ChevronDown,
	"chevron-up": ChevronUp,
	save: CircleCheck,
	close: X,
	logout: LogOut,
	more: Ellipsis,
	mic: Mic,
	minus: Minus,
	voice: AudioWaveform,
	share: Share,
	image: Image,
	globe: Globe,
	history: History,
	book: BookOpen,
	monitor: Monitor,
	pinOff: PinOff,
	trash: Trash2,
	smile: SmilePlus,
	graduation: GraduationCap,
	penTool: PenTool,
	sparkles: Sparkles,
	penLine: PenLine,
	squarePen: SquarePen,
	audioWaveform: AudioWaveform,
	ellipsis: Ellipsis,
	messageCircle: MessageCircle,
	help: HelpCircle,
	question: HelpCircle,
};

export function Icon({
	name,
	size = 24,
	color,
	weight: _weight,
}: {
	name: IconName;
	size?: number;
	color: string;
	weight?: string;
}) {
	const Lucide = ICONS[name] || HelpCircle;
	return (
		<Lucide
			color={color}
			size={size}
			strokeLinecap="round"
			strokeLinejoin="round"
			strokeWidth={2}
		/>
	);
}
