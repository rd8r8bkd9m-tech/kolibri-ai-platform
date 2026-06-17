import { motion } from "framer-motion";
import { BrainCircuit, Sparkles } from "lucide-react";
import { KolibriAvatar } from "@/components/kolibri/KolibriAvatar";
import { useChatStore } from "@/store/useChatStore";

export function ThinkingIndicator() {
  const steps = useChatStore((state) => state.thinkingSteps);
  const visibleSteps = steps.length
    ? steps
    : ["Слушаю запрос", "Ищу в цифровой памяти", "Формирую ответ"];

  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="mb-5 flex w-full justify-start">
      <div className="thought-bubble">
        <KolibriAvatar state="thinking" size="sm" className="mt-0.5 shrink-0" />
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
            <BrainCircuit className="h-4 w-4 text-emerald-600" />
            Kolibri размышляет
          </div>
          <div className="mt-2 grid gap-1.5">
            {visibleSteps.slice(-4).map((step, index) => (
              <motion.div
                key={`${step}-${index}`}
                initial={{ opacity: 0.45 }}
                animate={{ opacity: index === visibleSteps.length - 1 ? [0.55, 1, 0.55] : 0.72 }}
                transition={{ duration: 1.1, repeat: index === visibleSteps.length - 1 ? Infinity : 0 }}
                className="flex items-start gap-2 text-xs leading-5 text-muted"
              >
                <Sparkles className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-600" />
                <span>{step}</span>
              </motion.div>
            ))}
          </div>
        </div>
      </div>
    </motion.div>
  );
}
