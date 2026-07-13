export type Availability = 'available' | 'degraded' | 'unavailable';

export interface CapabilityRecord {
  id: string;
  name: string;
  description?: string;
  status: Availability;
  invocable: boolean;
  kind?: 'capability' | 'plugin' | 'skill' | 'tool';
}

export interface ProjectSummary {
  id: string;
  title: string;
  updatedAt: string;
}

export interface BootstrapSnapshot {
  sessionId?: string;
  projects: ProjectSummary[];
  capabilities: CapabilityRecord[];
}

export interface EstimateLine {
  id: string;
  title: string;
  unit: string;
  quantity: number;
  unitPriceRub: number;
  amountRub: number;
  section?: string;
}

export interface EstimateSummarySection {
  id: string;
  title: string;
  amountRub: number;
  icon?: 'foundation' | 'house' | 'engineering';
}

export interface EstimateArtifactData {
  title: string;
  location?: string;
  pricedAt?: string;
  status: 'preliminary' | 'verified';
  sourceSummary: string;
  lines: EstimateLine[];
  summarySections?: EstimateSummarySection[];
}

export interface VerifiedArtifact {
  id: string;
  name: string;
  mimeType: string;
  sizeBytes: number;
  sha256: string;
  downloadUrl: string;
  previewUrl?: string;
  kind?: 'file' | 'estimate';
  estimate?: EstimateArtifactData;
}

export type WorkStage =
  | 'queued'
  | 'planning'
  | 'working'
  | 'tool'
  | 'source'
  | 'verifying'
  | 'complete'
  | 'blocked'
  | 'cancelled';

export type WorkStageStatus = 'pending' | 'active' | 'complete' | 'failed';

export interface WorkTraceUpdate {
  id: string;
  stage: WorkStage;
  label: string;
  summary?: string;
  status: WorkStageStatus;
}

export interface ResponseRequest {
  input: string;
  previousResponseId?: string;
  projectId?: string;
  tools: string[];
  mode?: 'fast' | 'reasoning';
}

export interface ResponseStreamHandlers {
  onCreated(responseId: string): void;
  onTextDelta(delta: string): void;
  onTrace(update: WorkTraceUpdate): void;
  onArtifact(artifact: VerifiedArtifact): void;
  onCompleted(responseId?: string): void;
  onFailed(message: string): void;
}

export interface KolibriClient {
  bootstrap(signal?: AbortSignal): Promise<BootstrapSnapshot>;
  createProject(title: string, signal?: AbortSignal): Promise<ProjectSummary>;
  streamResponse(
    request: ResponseRequest,
    handlers: ResponseStreamHandlers,
    signal?: AbortSignal,
  ): Promise<void>;
  cancelResponse(responseId: string, signal?: AbortSignal): Promise<void>;
}
