import { apiRequest, apiUpload } from "./api-client";

export interface UploadResponse {
  jobId: string;
  documentId: string;
  versionId: string;
}

export interface ContractJob {
  id: string;
  documentId?: string;
  versionId?: string;
  filename: string;
  status: "uploading" | "parsing" | "extracting" | "retrieving" | "analyzing" | "verifying" | "completed" | "failed";
  progress: number;
  createdAt: string;
  fileUrl?: string;
  previewText?: string;
  sourceFormat?: string;
  clauses?: ContractClause[];
  matches?: LegalMatch[];
  compliance?: ComplianceResult;
  citations?: CitationResult[];
  error?: string;
}

export interface ContractClause {
  id: string;
  type: string;
  text: string;
  riskLevel: "low" | "medium" | "high";
}

export interface LegalMatch {
  clauseId: string;
  uid: string;
  citation: string;
  documentTitle: string;
  segmentType: string;
  score: number;
  rankingScore?: number;
  validitySignal: string;
  scoreFactors: Record<string, number>;
  text?: string;
}

export interface CitationResult {
  displayText: string;
  uid: string;
  verified: boolean;
  reason?: string;
  documentTitle?: string;
}

export interface ComplianceResult {
  violations: ComplianceViolation[];
  risks: string[];
  suggestions: string[];
  citations?: CitationResult[];
}

export interface ComplianceViolation {
  clause: string;
  description: string;
  citation: string;
  verified: boolean;
  contractClauseId?: string;
  contractClauseType?: string;
}

export interface JobStatusResponse {
  jobId: string;
  status: ContractJob["status"];
  progress: number;
  filename: string;
  createdAt: string;
  documentId?: string;
  versionId?: string;
  fileUrl?: string;
  previewText?: string;
  sourceFormat?: string;
  clauses?: ContractClause[];
  matches?: LegalMatch[];
  compliance?: ComplianceResult;
  citations?: CitationResult[];
  error?: string;
}

export async function uploadContract(file: File): Promise<UploadResponse> {
  const formData = new FormData();
  formData.append("file", file);
  return apiUpload<UploadResponse>("/api/contracts/upload", formData, { timeout: 60000 });
}

export async function getJobStatus(jobId: string): Promise<ContractJob> {
  const status = await apiRequest<JobStatusResponse>(`/api/contracts/${jobId}/status`);

  return {
    id: status.jobId,
    documentId: status.documentId,
    versionId: status.versionId,
    filename: status.filename,
    status: status.status,
    progress: status.progress,
    createdAt: status.createdAt,
    fileUrl: status.fileUrl,
    previewText: status.previewText,
    sourceFormat: status.sourceFormat,
    clauses: status.clauses,
    matches: status.matches,
    compliance: status.compliance,
    citations: status.citations,
    error: status.error,
  };
}

let jobHistoryRequest: Promise<ContractJob[]> | null = null;

export async function getJobHistory(): Promise<ContractJob[]> {
  if (jobHistoryRequest) return jobHistoryRequest;

  jobHistoryRequest = apiRequest<JobStatusResponse[]>("/api/contracts/history", {}, { timeout: 60000 })
    .then((jobs) => jobs.map((job) => ({
      id: job.jobId,
      documentId: job.documentId,
      versionId: job.versionId,
      filename: job.filename,
      status: job.status,
      progress: job.progress,
      createdAt: job.createdAt,
      fileUrl: job.fileUrl,
      previewText: job.previewText,
      sourceFormat: job.sourceFormat,
      clauses: job.clauses,
      matches: job.matches,
      compliance: job.compliance,
      citations: job.citations,
      error: job.error,
    })))
    .finally(() => {
      jobHistoryRequest = null;
    });

  return jobHistoryRequest;
}

export async function deleteDocument(documentId: string): Promise<void> {
  await apiRequest(`/api/contracts/documents/${documentId}`, { method: "DELETE" });
}

export const contractApi = {
  uploadContract,
  getJobStatus,
  getJobHistory,
  deleteDocument,
};
