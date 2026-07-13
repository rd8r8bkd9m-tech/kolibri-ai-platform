import type {
  BootstrapSnapshot,
  EstimateArtifactData,
  KolibriClient,
  ProjectSummary,
  ResponseRequest,
  ResponseStreamHandlers,
  VerifiedArtifact,
  WorkTraceUpdate,
} from '../api/types';
import type { ShellInitialView } from '../app/KolibriShell';
import type { ConversationMessage } from '../model/conversation';

export const DEV_FIXTURE_SENTINEL = '__KOLIBRI_DEV_ESTIMATE_FIXTURE__';

const DESKTOP_LINES: EstimateArtifactData['lines'] = [
  { id: 'foundation', title: 'Фундамент (ленточный ж/б)', unit: 'м³', quantity: 18, unitPriceRub: 8500, amountRub: 153000 },
  { id: 'walls', title: 'Стены (газобетон 400 мм с кладкой)', unit: 'м²', quantity: 250, unitPriceRub: 4200, amountRub: 1050000 },
  { id: 'roof', title: 'Кровля (металлочерепица с работой)', unit: 'м²', quantity: 120, unitPriceRub: 2750, amountRub: 330000 },
  { id: 'windows', title: 'Окна и двери (ПВХ)', unit: 'м²', quantity: 24, unitPriceRub: 12500, amountRub: 300000 },
  { id: 'engineering', title: 'Инженерные сети (электрика, водоснабжение, канализация)', unit: 'компл.', quantity: 1, unitPriceRub: 270000, amountRub: 270000 },
];

const MOBILE_LINES: EstimateArtifactData['lines'] = [
  { id: 'foundation', title: 'Фундамент', unit: 'компл.', quantity: 1, unitPriceRub: 228000, amountRub: 228000, section: 'Фундамент' },
  { id: 'shell', title: 'Коробка дома', unit: 'компл.', quantity: 1, unitPriceRub: 991200, amountRub: 991200, section: 'Коробка дома' },
  { id: 'engineering', title: 'Инженерные системы', unit: 'компл.', quantity: 1, unitPriceRub: 781000, amountRub: 781000, section: 'Инженерные системы' },
];

const PDF_BYTES = `%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj\n3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents 4 0 R>>endobj\n4 0 obj<</Length 44>>stream\nBT /F1 18 Tf 72 720 Td (Kolibri estimate) Tj ET\nendstream\nendobj\nxref\n0 5\n0000000000 65535 f \ntrailer<</Root 1 0 R/Size 5>>\nstartxref\n0\n%%EOF`;

function fixturePdfUrl(): string {
  return typeof URL.createObjectURL === 'function'
    ? URL.createObjectURL(new Blob([PDF_BYTES], { type: 'application/pdf' }))
    : '/v1/artifacts/dev-estimate/content';
}

function trace(mobile: boolean): WorkTraceUpdate[] {
  return mobile
    ? [
        { id: 'understood', stage: 'planning', label: 'Понял задачу', status: 'complete' },
        { id: 'data', stage: 'source', label: 'Собрал данные', status: 'complete' },
        { id: 'estimator', stage: 'tool', label: 'Сметчик — считает', status: 'complete' },
        { id: 'verifier', stage: 'verifying', label: 'Проверяющий — ожидает', status: 'active' },
      ]
    : [
        { id: 'understood', stage: 'planning', label: 'Понял задачу', status: 'complete' },
        { id: 'data', stage: 'source', label: 'Собрал данные', status: 'complete' },
        { id: 'estimate', stage: 'tool', label: 'Сформировал смету', status: 'complete' },
        { id: 'prices', stage: 'verifying', label: 'Проверил цены', status: 'complete' },
        { id: 'result', stage: 'complete', label: 'Подготовил результат', status: 'complete' },
      ];
}

function estimateArtifact(mobile: boolean): VerifiedArtifact {
  const estimate: EstimateArtifactData = mobile
    ? {
        title: 'Предварительная смета',
        location: 'Лениногорск',
        pricedAt: '12.07.2026',
        status: 'verified',
        sourceSummary: 'Источники: проверены и актуальны',
        lines: MOBILE_LINES,
        summarySections: [
          { id: 'foundation', title: 'Фундамент', amountRub: 228000, icon: 'foundation' },
          { id: 'shell', title: 'Коробка дома', amountRub: 991200, icon: 'house' },
          { id: 'engineering', title: 'Инженерные системы', amountRub: 781000, icon: 'engineering' },
        ],
      }
    : {
        title: 'Предварительная смета · дом 100 м²',
        location: 'Лениногорск',
        pricedAt: '12.07.2026',
        status: 'verified',
        sourceSummary: 'Источники: актуальные прайс-листы поставщиков и открытые сметные базы города Лениногорск.',
        lines: DESKTOP_LINES,
      };
  return {
    id: `fixture-estimate-${mobile ? 'mobile' : 'desktop'}`,
    name: 'Смета_дом_100м2_Лениногорск_12.07.2026.pdf',
    mimeType: 'application/pdf',
    sizeBytes: 124 * 1024,
    sha256: 'e'.repeat(64),
    downloadUrl: fixturePdfUrl(),
    kind: 'estimate',
    estimate,
  };
}

function message(
  id: string,
  role: ConversationMessage['role'],
  content: string,
  createdAt: string,
  extras: Partial<ConversationMessage> = {},
): ConversationMessage {
  return {
    id,
    role,
    content,
    createdAt,
    status: role === 'assistant' ? 'complete' : 'complete',
    trace: [],
    artifacts: [],
    ...extras,
  };
}

class EstimateFixtureClient implements KolibriClient {
  private readonly snapshot: BootstrapSnapshot;

  constructor(project: ProjectSummary) {
    this.snapshot = {
      sessionId: 'dev-fixture-session',
      projects: [project],
      capabilities: [
        { id: 'web_search', name: 'Интернет', status: 'available', invocable: true },
        { id: 'document', name: 'Документы', status: 'available', invocable: true },
        { id: 'image_generation', name: 'Изображения', status: 'available', invocable: true },
        { id: 'speech', name: 'Голос', status: 'available', invocable: true },
      ],
    };
  }

  async bootstrap(): Promise<BootstrapSnapshot> { return this.snapshot; }

  async createProject(title: string): Promise<ProjectSummary> {
    return { id: 'fixture-new-project', title, updatedAt: '2026-07-12T08:42:00Z' };
  }

  async streamResponse(
    request: ResponseRequest,
    handlers: ResponseStreamHandlers,
  ): Promise<void> {
    handlers.onCreated('fixture-response');
    handlers.onTrace({ id: 'fixture-live', stage: 'working', label: 'Выполняю задачу', status: 'active' });
    handlers.onTextDelta(`Принял: ${request.input}`);
    handlers.onTrace({ id: 'fixture-live', stage: 'working', label: 'Выполнил задачу', status: 'complete' });
    handlers.onCompleted('fixture-response');
  }

  async cancelResponse(): Promise<void> {}
}

export function createEstimateVisualFixture(mobile: boolean): {
  client: KolibriClient;
  initialView: ShellInitialView;
} {
  void DEV_FIXTURE_SENTINEL;
  const project: ProjectSummary = {
    id: 'project-house-100',
    title: mobile ? 'Дом 100 м²' : 'Дом 100 м² · Лениногорск',
    updatedAt: '2026-07-12T08:42:00Z',
  };
  const artifact = estimateArtifact(mobile);
  const createdAt = mobile ? '2026-07-12T11:24:00+03:00' : '2026-07-12T11:42:00+03:00';
  const messages = mobile
    ? [
        message('fixture-user', 'user', 'гамбургер динамично\nменяется на птичку\nи наоборот как в gpt', createdAt),
        message('fixture-assistant', 'assistant', 'Понял задачу. Реализую динамическую\nсмену иконки между гамбургером\nи птицей, как в GPT.', createdAt, {
          status: 'streaming',
          trace: trace(true),
          artifacts: [artifact],
        }),
      ]
    : [
        message('fixture-user', 'user', 'Сделай предварительную смету на строительство\nдома 100 м² в Лениногорске.', createdAt),
        message('fixture-assistant', 'assistant', 'Готово. Подготовил предварительную смету на дом 100 м² в Лениногорске.\nНиже — ключевые разделы и итоговая стоимость.', createdAt, {
          trace: trace(false),
          artifacts: [artifact],
        }),
      ];
  return {
    client: new EstimateFixtureClient(project),
    initialView: { project, conversation: { messages, previousResponseId: 'fixture-response' } },
  };
}
