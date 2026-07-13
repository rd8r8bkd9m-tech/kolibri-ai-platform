import type {
  BootstrapSnapshot,
  KolibriClient,
  ProjectSummary,
  ResponseRequest,
  ResponseStreamHandlers,
} from '../api/types';

const SHA = 'a'.repeat(64);

export class FakeKolibriClient implements KolibriClient {
  requests: ResponseRequest[] = [];
  cancelled: string[] = [];

  constructor(
    readonly snapshot: BootstrapSnapshot = {
      projects: [],
      capabilities: [],
    },
    readonly holdStream = false,
  ) {}

  async bootstrap(): Promise<BootstrapSnapshot> {
    return this.snapshot;
  }

  async createProject(title: string): Promise<ProjectSummary> {
    return { id: 'project-created', title, updatedAt: '2026-07-12T00:00:00Z' };
  }

  async streamResponse(
    request: ResponseRequest,
    handlers: ResponseStreamHandlers,
    signal?: AbortSignal,
  ): Promise<void> {
    this.requests.push(request);
    handlers.onCreated('response-1');
    handlers.onTrace({
      id: 'planning',
      stage: 'planning',
      label: 'Составляю план',
      status: 'complete',
    });
    handlers.onTrace({
      id: 'verification',
      stage: 'verifying',
      label: 'Проверяю результат',
      status: 'active',
    });
    handlers.onTextDelta('Готовый ответ Kolibri.');
    handlers.onArtifact({
      id: 'artifact-1',
      name: 'Результат.pdf',
      mimeType: 'application/pdf',
      sizeBytes: 2048,
      sha256: SHA,
      downloadUrl: '/v1/artifacts/artifact-1/content',
    });
    if (this.holdStream) {
      await new Promise<void>((resolve, reject) => {
        if (signal?.aborted) reject(new DOMException('Aborted', 'AbortError'));
        signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')), {
          once: true,
        });
      });
      return;
    }
    handlers.onTrace({
      id: 'verification',
      stage: 'verifying',
      label: 'Проверяю результат',
      status: 'complete',
    });
    handlers.onCompleted('response-1');
  }

  async cancelResponse(responseId: string): Promise<void> {
    this.cancelled.push(responseId);
  }
}
