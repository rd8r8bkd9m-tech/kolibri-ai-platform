import {
  ArrowUp,
  BrainCircuit,
  Check,
  ChevronDown,
  Mic,
  Plus,
  Square,
  X,
  Zap,
} from 'lucide-react';
import { useMemo, useRef, useState } from 'react';
import type { CapabilityRecord } from '../api/types';

interface SpeechResultEvent {
  results: ArrayLike<{ 0: { transcript: string } }>;
}

interface SpeechRecognitionLike {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  onresult: ((event: SpeechResultEvent) => void) | null;
  onend: (() => void) | null;
  start(): void;
  stop(): void;
}

type SpeechRecognitionConstructor = new () => SpeechRecognitionLike;

interface ComposerProps {
  capabilities: CapabilityRecord[];
  presentation: 'mobile' | 'desktop';
  disabled?: boolean;
  busy: boolean;
  onSend(input: string, tools: string[], mode: 'fast' | 'reasoning'): void;
  onStop(): void;
}

export function Composer({
  capabilities,
  presentation,
  disabled,
  busy,
  onSend,
  onStop,
}: ComposerProps) {
  const [value, setValue] = useState('');
  const [toolsOpen, setToolsOpen] = useState(false);
  const [modeOpen, setModeOpen] = useState(false);
  const [mode, setMode] = useState<'fast' | 'reasoning'>(presentation === 'mobile' ? 'reasoning' : 'fast');
  const [listening, setListening] = useState(false);
  const [selectedTools, setSelectedTools] = useState<string[]>([]);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const speechRef = useRef<SpeechRecognitionLike | null>(null);
  const invocableTools = useMemo(
    () => capabilities.filter(
      (item) => item.invocable && (item.status === 'available' || item.status === 'degraded'),
    ),
    [capabilities],
  );
  const speechAvailable = invocableTools.some((item) => /(?:speech|voice|audio|microphone)/i.test(item.id));
  const speechConstructor = typeof window === 'undefined'
    ? undefined
    : (window as typeof window & {
        SpeechRecognition?: SpeechRecognitionConstructor;
        webkitSpeechRecognition?: SpeechRecognitionConstructor;
      }).SpeechRecognition ?? (window as typeof window & {
        webkitSpeechRecognition?: SpeechRecognitionConstructor;
      }).webkitSpeechRecognition;

  const toggleVoice = () => {
    if (speechRef.current) {
      speechRef.current.stop();
      speechRef.current = null;
      setListening(false);
      return;
    }
    if (!speechConstructor) return;
    const recognition = new speechConstructor();
    recognition.lang = 'ru-RU';
    recognition.interimResults = false;
    recognition.continuous = false;
    recognition.onresult = (event) => {
      const transcript = Array.from(event.results).map((result) => result[0]?.transcript ?? '').join(' ').trim();
      if (transcript) setValue((current) => [current.trim(), transcript].filter(Boolean).join(' '));
    };
    recognition.onend = () => {
      speechRef.current = null;
      setListening(false);
    };
    speechRef.current = recognition;
    setListening(true);
    recognition.start();
  };

  const submit = () => {
    const clean = value.trim();
    if (!clean || disabled || busy) return;
    onSend(clean, selectedTools, mode);
    setValue('');
    if (textareaRef.current) textareaRef.current.style.height = '';
  };

  const toggleTool = (id: string) => {
    setSelectedTools((current) =>
      current.includes(id) ? current.filter((item) => item !== id) : [...current, id],
    );
  };

  return (
    <footer className="composer-region" aria-label="Сообщение Kolibri">
      <div className="composer-wrap">
        {selectedTools.length ? (
          <div className="selected-tools" aria-label="Выбранные инструменты">
            {selectedTools.map((id) => {
              const tool = invocableTools.find((item) => item.id === id);
              if (!tool) return null;
              return (
                <button key={id} type="button" onClick={() => toggleTool(id)}>
                  {tool.name}<X aria-hidden="true" />
                </button>
              );
            })}
          </div>
        ) : null}

        <div className={`composer${busy ? ' is-busy' : ''}`}>
          <textarea
            ref={textareaRef}
            value={value}
            aria-label="Сообщение"
            placeholder={disabled
              ? 'Подключаю Kolibri…'
              : presentation === 'mobile'
                ? 'Уточнить или изменить...'
                : 'Скажите, что нужно сделать...'}
            disabled={disabled}
            rows={1}
            onChange={(event) => setValue(event.target.value)}
            onInput={(event) => {
              const target = event.currentTarget;
              target.style.height = '0px';
              target.style.height = `${Math.min(target.scrollHeight, 144)}px`;
            }}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
                event.preventDefault();
                submit();
              }
            }}
          />

          <div className="composer-controls">
            {invocableTools.length ? (
              <div className="tool-picker-anchor">
                <button
                  className="composer-icon-button"
                  type="button"
                  aria-label="Инструменты"
                  aria-expanded={toolsOpen}
                  onClick={() => setToolsOpen((open) => !open)}
                >
                  <Plus aria-hidden="true" />
                </button>
                {toolsOpen ? (
                  <div className="tool-picker" role="menu" aria-label="Доступные инструменты">
                    {invocableTools.map((tool) => {
                      const selected = selectedTools.includes(tool.id);
                      return (
                        <button
                          key={tool.id}
                          type="button"
                          role="menuitemcheckbox"
                          aria-checked={selected}
                          onClick={() => toggleTool(tool.id)}
                        >
                          <span><strong>{tool.name}</strong>{tool.description ? <small>{tool.description}</small> : null}</span>
                          {selected ? <Check aria-hidden="true" /> : null}
                        </button>
                      );
                    })}
                  </div>
                ) : null}
              </div>
            ) : <span className="composer-control-spacer" />}

            <div className="mode-picker-anchor">
              <button
                className="mode-button"
                type="button"
                aria-label="Режим ответа"
                aria-expanded={modeOpen}
                onClick={() => setModeOpen((open) => !open)}
              >
                {mode === 'fast' ? <Zap aria-hidden="true" /> : <BrainCircuit aria-hidden="true" />}
                <span>{mode === 'fast' ? 'Быстро' : 'Рассуждение'}</span>
                <ChevronDown aria-hidden="true" />
              </button>
              {modeOpen ? (
                <div className="mode-picker" role="menu" aria-label="Режим ответа">
                  <button type="button" role="menuitemradio" aria-checked={mode === 'fast'} onClick={() => { setMode('fast'); setModeOpen(false); }}>
                    <Zap aria-hidden="true" /><span><strong>Быстро</strong><small>Короткий путь к ответу</small></span>
                  </button>
                  <button type="button" role="menuitemradio" aria-checked={mode === 'reasoning'} onClick={() => { setMode('reasoning'); setModeOpen(false); }}>
                    <BrainCircuit aria-hidden="true" /><span><strong>Рассуждение</strong><small>Глубокая проверка задачи</small></span>
                  </button>
                </div>
              ) : null}
            </div>

            <span className="composer-flex-spacer" />
            {presentation === 'desktop' && speechAvailable && speechConstructor ? (
              <button
                className={`voice-button${listening ? ' is-listening' : ''}`}
                type="button"
                aria-label={listening ? 'Остановить голосовой ввод' : 'Голосовой ввод'}
                onClick={toggleVoice}
              >
                <Mic aria-hidden="true" />
              </button>
            ) : null}
            {busy ? (
              <button className="send-button stop-button" type="button" aria-label="Остановить" onClick={onStop}>
                <Square aria-hidden="true" fill="currentColor" />
              </button>
            ) : (
              <button className="send-button" type="button" aria-label="Отправить" disabled={disabled || !value.trim()} onClick={submit}>
                <ArrowUp aria-hidden="true" />
              </button>
            )}
          </div>
        </div>
      </div>
    </footer>
  );
}
