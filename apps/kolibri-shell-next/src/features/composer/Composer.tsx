import type { ComposerMode, RuntimeStatus } from "@domain/shell";
import { ArrowUp, ChevronDown, Lightbulb, Mic, Paperclip, Plus, X, Zap } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";

interface ComposerProps {
  runtimeStatus: RuntimeStatus;
  sending: boolean;
  onSend: (draft: { content: string; mode: ComposerMode; attachmentNames: string[] }) => Promise<boolean>;
  onNotice: (message: string) => void;
}

interface SpeechResultEvent {
  results: ArrayLike<{ 0: { transcript: string } }>;
}

interface SpeechRecognitionLike {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onresult: ((event: SpeechResultEvent) => void) | null;
  onerror: (() => void) | null;
  onend: (() => void) | null;
  start(): void;
  stop(): void;
}

type SpeechRecognitionConstructor = new () => SpeechRecognitionLike;
type SpeechWindow = Window & {
  SpeechRecognition?: SpeechRecognitionConstructor;
  webkitSpeechRecognition?: SpeechRecognitionConstructor;
};

function compactViewport(): boolean {
  return typeof window.matchMedia === "function" && window.matchMedia("(max-width: 700px)").matches;
}

export function Composer({ runtimeStatus, sending, onSend, onNotice }: ComposerProps) {
  const [text, setText] = useState("");
  const [mode, setMode] = useState<ComposerMode>(() => compactViewport() ? "reasoning" : "fast");
  const [compact, setCompact] = useState(compactViewport);
  const [attachmentNames, setAttachmentNames] = useState<string[]>([]);
  const [attachmentMenuOpen, setAttachmentMenuOpen] = useState(false);
  const [modeMenuOpen, setModeMenuOpen] = useState(false);
  const [recording, setRecording] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const recognition = useRef<SpeechRecognitionLike | null>(null);

  useEffect(() => {
    if (typeof window.matchMedia !== "function") return undefined;
    const query = window.matchMedia("(max-width: 700px)");
    const update = () => setCompact(query.matches);
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);

  useEffect(() => () => recognition.current?.stop(), []);

  const submit = async (event?: FormEvent) => {
    event?.preventDefault();
    const sent = await onSend({ content: text, mode, attachmentNames });
    if (sent) {
      setText("");
      setAttachmentNames([]);
    }
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void submit();
    }
  };

  const toggleVoice = () => {
    if (recognition.current && recording) {
      recognition.current.stop();
      return;
    }
    const speechWindow = window as SpeechWindow;
    const Recognition = speechWindow.SpeechRecognition ?? speechWindow.webkitSpeechRecognition;
    if (!Recognition) {
      onNotice("Голосовой ввод не поддерживается этим браузером.");
      return;
    }
    const instance = new Recognition();
    instance.lang = "ru-RU";
    instance.continuous = false;
    instance.interimResults = false;
    instance.onresult = (event) => {
      const transcript = event.results[0]?.[0]?.transcript;
      if (transcript) setText((value) => `${value}${value ? " " : ""}${transcript}`);
    };
    instance.onerror = () => onNotice("Не удалось распознать речь. Попробуйте ещё раз.");
    instance.onend = () => {
      setRecording(false);
      recognition.current = null;
    };
    recognition.current = instance;
    setRecording(true);
    instance.start();
  };

  const ready = runtimeStatus === "ready";
  const canSend = ready && text.trim().length > 0 && !sending;

  return (
    <form className="composer" onSubmit={(event) => void submit(event)} aria-label="Сообщение Kolibri">
      {attachmentNames.length > 0 ? (
        <div className="attachment-chips">
          {attachmentNames.map((name) => (
            <span key={name}>
              <Paperclip aria-hidden="true" />
              {name}
              <button
                type="button"
                aria-label={`Убрать ${name}`}
                onClick={() => setAttachmentNames((items) => items.filter((item) => item !== name))}
              >
                <X aria-hidden="true" />
              </button>
            </span>
          ))}
        </div>
      ) : null}
      <textarea
        value={text}
        onChange={(event) => setText(event.currentTarget.value)}
        onKeyDown={onKeyDown}
        rows={1}
        aria-label="Сообщение"
        placeholder={compact ? "Уточнить или изменить..." : "Скажите, что нужно сделать..."}
        disabled={!ready}
      />
      <div className="composer-controls">
        <div className="composer-menu-wrap">
          <button
            type="button"
            className="composer-circle add-button"
            aria-label="Добавить"
            aria-expanded={attachmentMenuOpen}
            onClick={() => setAttachmentMenuOpen((open) => !open)}
          >
            <Plus aria-hidden="true" />
          </button>
          {attachmentMenuOpen ? (
            <div className="composer-popover attachment-popover" role="menu">
              <button
                type="button"
                role="menuitem"
                onClick={() => {
                  fileInput.current?.click();
                  setAttachmentMenuOpen(false);
                }}
              >
                <Paperclip aria-hidden="true" />
                Прикрепить файл
              </button>
            </div>
          ) : null}
          <input
            ref={fileInput}
            className="visually-hidden"
            type="file"
            multiple
            onChange={(event) => {
              const names = Array.from(event.currentTarget.files ?? []).map((file) => file.name);
              setAttachmentNames(names);
              if (names.length) onNotice(`Добавлено файлов: ${names.length}`);
            }}
          />
        </div>

        <div className="composer-menu-wrap mode-wrap">
          <button
            className="mode-button"
            type="button"
            aria-expanded={modeMenuOpen}
            onClick={() => setModeMenuOpen((open) => !open)}
          >
            <span className="mode-icon">{mode === "fast" ? <Zap aria-hidden="true" /> : <Lightbulb aria-hidden="true" />}</span>
            {mode === "fast" ? "Быстро" : "Рассуждение"}
            <ChevronDown aria-hidden="true" />
          </button>
          {modeMenuOpen ? (
            <div className="composer-popover mode-popover" role="menu">
              <button type="button" role="menuitemradio" aria-checked={mode === "fast"} onClick={() => { setMode("fast"); setModeMenuOpen(false); }}>
                <Zap aria-hidden="true" /> Быстро
              </button>
              <button type="button" role="menuitemradio" aria-checked={mode === "reasoning"} onClick={() => { setMode("reasoning"); setModeMenuOpen(false); }}>
                <Lightbulb aria-hidden="true" /> Рассуждение
              </button>
            </div>
          ) : null}
        </div>

        <span className="composer-spacer" />
        <button
          type="button"
          className={`composer-circle voice-button ${recording ? "is-recording" : ""}`}
          aria-label={recording ? "Остановить запись" : "Голосовой ввод"}
          aria-pressed={recording}
          onClick={toggleVoice}
          disabled={!ready}
        >
          <Mic aria-hidden="true" />
        </button>
        <button className="composer-circle send-button" type="submit" aria-label="Отправить" disabled={!canSend}>
          <ArrowUp aria-hidden="true" />
        </button>
      </div>
    </form>
  );
}
