import type { ComposerMode, ShellEvent } from "@domain/shell";

export interface SendMessageInput {
  content: string;
  mode: ComposerMode;
  attachmentNames: string[];
  clientMessageId: string;
}

export type EmitShellEvent = (event: ShellEvent) => void;

export interface ShellClient {
  start(emit: EmitShellEvent, signal: AbortSignal): Promise<() => void>;
  send(input: SendMessageInput, emit: EmitShellEvent, signal: AbortSignal): Promise<void>;
}
