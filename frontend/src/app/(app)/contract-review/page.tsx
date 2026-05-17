"use client";

import { useState, useCallback, useRef, useEffect, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useSearchParams } from "next/navigation";
import { WobblyButton } from "@/components/ui/wobbly-button";
import { WobblyCard } from "@/components/ui/wobbly-card";
import { WobblyBadge } from "@/components/ui/wobbly-badge";
import { Upload, FileText, CheckCircle, AlertTriangle, XCircle, ChevronDown, ChevronRight, Eye, ArrowLeft, FileText as FileTextIcon, Type, Loader2, BookOpen, X, Clock, Trash2 } from "lucide-react";
import dynamic from "next/dynamic";
import { cn } from "@/lib/utils";
import { fileToPdfBlob } from "@/lib/file-to-pdf";

const PDFViewer = dynamic(() => import("@/components/contract/pdf-viewer").then(m => m.PDFViewer), { ssr: false });

type ViewMode = "upload" | "preview" | "analyzing" | "results" | "history";
type InputType = "file" | "text";

interface Clause {
  id: string;
  type: string;
  text: string;
  riskLevel: "low" | "medium" | "high";
}

interface ComplianceResult {
  violations: { clause: string; description: string; citation: string; verified: boolean; contractClauseId?: string; contractClauseType?: string }[];
  risks: string[];
  suggestions: string[];
}

interface LegalDocument {
  title: string;
  so_ky_hieu: string;
  loai_van_ban: string;
  ngay_ban_hanh: string;
  co_quan_ban_hanh: string;
  articles: LegalArticle[];
}

interface LegalArticle {
  uid: string;
  index: number;
  title: string;
  text: string;
  clauses: LegalClause[];
}

interface LegalClause {
  uid: string;
  index: number;
  text: string;
  points: LegalPoint[];
}

interface LegalPoint {
  uid: string;
  letter: string;
  text: string;
}

import { contractApi } from "@/lib/api-contract";
import type { CitationResult, ContractJob, LegalMatch } from "@/lib/api-contract";

type AnalyzeStatus = ContractJob["status"];

const analyzeSteps = [
  { status: "uploading", label: "Đang tải lên tài liệu" },
  { status: "parsing", label: "Đang đọc và trích xuất nội dung" },
  { status: "extracting", label: "Đang phân tích điều khoản" },
  { status: "retrieving", label: "Đang đối chiếu pháp luật" },
  { status: "analyzing", label: "Đang đánh giá rủi ro" },
  { status: "verifying", label: "Đang xác minh căn cứ" },
  { status: "completed", label: "Hoàn thành" },
] as const;

export default function ContractReviewPage() {
  const searchParams = useSearchParams();
  const [viewMode, setViewMode] = useState<ViewMode>("upload");
  const [inputType, setInputType] = useState<InputType>("file");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [textContent, setTextContent] = useState("");
  const [progress, setProgress] = useState(0);
  const [currentStatus, setCurrentStatus] = useState<AnalyzeStatus>("uploading");
  const [splitPosition, setSplitPosition] = useState(50);
  const [isDragging, setIsDragging] = useState(false);
  const [expandedClauses, setExpandedClauses] = useState<Set<string>>(new Set());
  const [expandedMatches, setExpandedMatches] = useState<Set<string>>(new Set());
  const [clauses, setClauses] = useState<Clause[]>([]);
  const [compliance, setCompliance] = useState<ComplianceResult | null>(null);
  const [legalMatches, setLegalMatches] = useState<LegalMatch[]>([]);
  const [citations, setCitations] = useState<CitationResult[]>([]);
  const [sourceName, setSourceName] = useState("");
  const [converting, setConverting] = useState(false);
  const [highlightedClauseId, setHighlightedClauseId] = useState<string | null>(null);
  const [expandedRisks, setExpandedRisks] = useState(false);
  const [expandedSuggestions, setExpandedSuggestions] = useState(false);
  const [selectedDocument, setSelectedDocument] = useState<LegalDocument | null>(null);
  const [documentLoading, setDocumentLoading] = useState(false);
  const [jobHistory, setJobHistory] = useState<ContractJob[]>([]);
  const [deletingDocumentIds, setDeletingDocumentIds] = useState<Set<string>>(new Set());
  const [currentJobId, setCurrentJobId] = useState<string | null>(null);
  const [currentDocumentId, setCurrentDocumentId] = useState<string | null>(null);
  const [snapshotError, setSnapshotError] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    };
  }, [previewUrl]);

  useEffect(() => {
    loadJobHistory();
  }, []);

  useEffect(() => {
    const requestedJobId = searchParams.get("jobId");
    const savedJobId = localStorage.getItem("lastJobId");
    const targetJobId = requestedJobId || savedJobId;
    if (targetJobId) {
      loadJobResult(targetJobId);
    }
  }, [searchParams]);

  const loadJobHistory = async () => {
    try {
      const history = await contractApi.getJobHistory();
      setJobHistory(history || []);
    } catch (err) {
      console.error("Failed to load history:", err);
    }
  };

  const notifyContractHistoryChanged = () => {
    window.dispatchEvent(new Event("contract-review:history-changed"));
  };

  const loadJobResult = async (jobId: string) => {
    try {
      const status = await contractApi.getJobStatus(jobId);
      if (status.status === "completed") {
        await hydrateCompletedJob(status);
      } else if (status.status === "failed") {
        setCurrentJobId(status.id);
        setCurrentDocumentId(status.documentId || null);
        setSourceName(status.filename || "");
        setClauses([]);
        setExpandedMatches(new Set());
        setCompliance(null);
        setLegalMatches([]);
        setCitations([]);
        setSnapshotError(status.error || "Không thể tải kết quả rà soát trước đó.");
        setViewMode("results");
      }
    } catch (err) {
      console.error("Failed to load job result:", err);
      setSnapshotError("Không thể tải kết quả rà soát đã lưu.");
    }
  };

  const hydrateCompletedJob = async (status: ContractJob) => {
    const apiClauses = status.clauses || [];
    const apiCompliance = status.compliance;
    setLegalMatches(status.matches || []);
    setCitations(status.citations || apiCompliance?.citations || []);
    setClauses(
      apiClauses.map((c) => ({
        id: c.id,
        type: c.type,
        text: c.text,
        riskLevel: c.riskLevel,
      }))
    );
    setCompliance(
      apiCompliance
        ? {
            violations: apiCompliance.violations.map((v) => ({
              clause: v.clause,
              description: v.description,
              citation: v.citation,
              verified: v.verified,
              contractClauseId: v.contractClauseId,
              contractClauseType: v.contractClauseType,
            })),
            risks: apiCompliance.risks,
            suggestions: apiCompliance.suggestions,
          }
        : null
    );
    const pdfPreviewUrl = await buildRestoredPreviewUrl(status);
    setPreviewUrl((prev) => {
      if (prev && prev.startsWith("blob:")) URL.revokeObjectURL(prev);
      return pdfPreviewUrl;
    });
    setTextContent(status.previewText || "");
    setSourceName(status.filename || "");
    setCurrentJobId(status.id);
    setCurrentDocumentId(status.documentId || null);
    setCurrentStatus("completed");
    setProgress(100);
    setSnapshotError(null);
    localStorage.setItem("lastJobId", status.id);
    setViewMode("results");
  };

  const buildRestoredPreviewUrl = async (status: ContractJob): Promise<string | null> => {
    if (!status.fileUrl) return null;
    if (status.sourceFormat === "pdf") return status.fileUrl;

    try {
      const response = await fetch(status.fileUrl);
      if (!response.ok) throw new Error(`Could not fetch stored file: ${response.status}`);

      const blob = await response.blob();
      const restoredFile = new File([blob], status.filename || "contract", {
        type: blob.type || "application/octet-stream",
      });
      const pdfBlob = await fileToPdfBlob(restoredFile);
      return URL.createObjectURL(pdfBlob);
    } catch (error) {
      console.error("Could not rebuild stored file preview:", error);
      return null;
    }
  };

  const resetToUpload = () => {
    if (previewUrl?.startsWith("blob:")) URL.revokeObjectURL(previewUrl);
    setSelectedFile(null);
    setPreviewUrl(null);
    setTextContent("");
    setClauses([]);
    setExpandedMatches(new Set());
    setCompliance(null);
    setLegalMatches([]);
    setCitations([]);
    setSourceName("");
    setProgress(0);
    setCurrentStatus("uploading");
    setViewMode("upload");
    setHighlightedClauseId(null);
    setExpandedRisks(false);
    setExpandedSuggestions(false);
    setSelectedDocument(null);
    setCurrentJobId(null);
    setCurrentDocumentId(null);
    setSnapshotError(null);
    localStorage.removeItem("lastJobId");
  };

  const handleFile = async (file: File) => {
    if (!file.name.match(/\.(pdf|docx|doc|txt|md)$/i)) {
      alert("Chỉ hỗ trợ file PDF, DOCX, DOC, TXT, MD");
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      alert("File quá lớn. Tối đa 10MB");
      return;
    }
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setSelectedFile(file);
    setTextContent("");
    setPreviewUrl(null);
    setSourceName(file.name);

    const ext = file.name.toLowerCase().split(".").pop();

    if (ext === "pdf") {
      setPreviewUrl(URL.createObjectURL(file));
      setViewMode("preview");
    } else {
      setConverting(true);
      try {
        const pdfBlob = await fileToPdfBlob(file);
        setPreviewUrl(URL.createObjectURL(pdfBlob));
        setViewMode("preview");
      } catch (err) {
        console.error("Conversion failed:", err);
        alert("Không thể chuyển đổi file. Vui lòng thử lại.");
      } finally {
        setConverting(false);
      }
    }
  };

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  }, []);

  const handleSelectFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
  };

  const handleAnalyze = async () => {
    if (!selectedFile && !textContent.trim()) return;

    setViewMode("analyzing");
    setProgress(0);
    setCurrentStatus("uploading");
    setSnapshotError(null);

    try {
      let jobId: string;
      let documentId: string | null = null;

      if (selectedFile) {
        const uploadResp = await contractApi.uploadContract(selectedFile);
        jobId = uploadResp.jobId;
        documentId = uploadResp.documentId;
      } else {
        const blob = new Blob([textContent], { type: "text/markdown" });
        const file = new File([blob], "contract.md", { type: "text/markdown" });
        const uploadResp = await contractApi.uploadContract(file);
        jobId = uploadResp.jobId;
        documentId = uploadResp.documentId;
      }

      setCurrentJobId(jobId);
      setCurrentDocumentId(documentId);
      localStorage.setItem("lastJobId", jobId);

      const pollInterval = setInterval(async () => {
        try {
          const status = await contractApi.getJobStatus(jobId);
          setProgress(status.progress);
          setCurrentStatus(status.status);

          if (status.status === "completed") {
            clearInterval(pollInterval);
            await hydrateCompletedJob(status);
            loadJobHistory();
            notifyContractHistoryChanged();
          } else if (status.status === "failed") {
            clearInterval(pollInterval);
            setSnapshotError(status.error || "Phân tích thất bại. Vui lòng thử lại.");
            setClauses([]);
            setExpandedMatches(new Set());
            setCompliance(null);
            setLegalMatches([]);
            setCitations([]);
            setSourceName(status.filename || sourceName);
            setViewMode("results");
            loadJobHistory();
            notifyContractHistoryChanged();
          }
        } catch (err) {
          console.error("Poll error:", err);
        }
      }, 1000);

      setTimeout(() => {
        clearInterval(pollInterval);
      }, 5 * 60 * 1000);
    } catch (err) {
      console.error("Upload failed:", err);
      alert("Không thể tải lên hợp đồng. Vui lòng thử lại.");
      setViewMode("preview");
    }
  };

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  useEffect(() => {
    if (!isDragging) return;
    const handleMouseMove = (e: MouseEvent) => {
      if (!containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const pct = Math.min(Math.max((x / rect.width) * 100, 20), 80);
      setSplitPosition(pct);
    };
    const handleMouseUp = () => setIsDragging(false);
    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);
    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };
  }, [isDragging]);

  const toggleClause = (id: string) => {
    setExpandedClauses((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const toggleMatch = (id: string) => {
    setExpandedMatches((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const riskColor = (level: string) => {
    if (level === "high") return "bg-accent/20 border-accent text-accent";
    if (level === "medium") return "bg-yellow-200/50 border-yellow-500 text-yellow-700";
    return "bg-green-100/50 border-green-500 text-green-700";
  };

  const highlightText = (text: string) => {
    if (!clauses.length) return text;
    let result = text;
    clauses.forEach((clause) => {
      const isHighlighted = clause.id === highlightedClauseId;
      const color = isHighlighted
        ? "bg-accent/50 ring-2 ring-accent"
        : clause.riskLevel === "high"
        ? "bg-accent/20"
        : clause.riskLevel === "medium"
        ? "bg-yellow-200/30"
        : "bg-green-100/30";
      const escaped = clause.text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      const regex = new RegExp(`(${escaped})`, "g");
      result = result.replace(regex, `<span class="${color} px-1 rounded transition-all duration-300">$1</span>`);
    });
    return result;
  };

  const uniqueDocuments = useMemo(() => {
    const docMap = new Map<string, { title: string; citations: CitationResult[] }>();
    citations.forEach((c) => {
      const docTitle = c.documentTitle || "Văn bản pháp luật";
      if (!docMap.has(docTitle)) {
        docMap.set(docTitle, { title: docTitle, citations: [] });
      }
      docMap.get(docTitle)!.citations.push(c);
    });
    return Array.from(docMap.values());
  }, [citations]);

  const loadDocumentContent = async (docTitle: string) => {
    setDocumentLoading(true);
    try {
      const encodedTitle = encodeURIComponent(docTitle);
      const response = await fetch(`/api/contracts/documents/${encodedTitle}`);
      if (response.ok) {
        const data = await response.json();
        setSelectedDocument(data);
      } else {
        alert("Không thể tải nội dung văn bản");
      }
    } catch (err) {
      console.error("Failed to load document:", err);
      alert("Lỗi khi tải nội dung văn bản");
    } finally {
      setDocumentLoading(false);
    }
  };

  const handleDeleteDocument = async (documentId: string) => {
    if (deletingDocumentIds.has(documentId)) return;

    const previousHistory = jobHistory;
    setDeletingDocumentIds((prev) => new Set(prev).add(documentId));
    setJobHistory((prev) => prev.filter((job) => job.documentId !== documentId));
    notifyContractHistoryChanged();
    if (currentDocumentId === documentId) {
      resetToUpload();
    }

    try {
      await contractApi.deleteDocument(documentId);
    } catch (err) {
      console.error("Failed to delete contract document:", err);
      setJobHistory(previousHistory);
      alert("Không thể xóa tài liệu lúc này.");
    } finally {
      setDeletingDocumentIds((prev) => {
        const next = new Set(prev);
        next.delete(documentId);
        return next;
      });
    }
  };

  const currentStepIndex = Math.max(0, analyzeSteps.findIndex((s) => s.status === currentStatus));
  const currentStep = analyzeSteps[currentStepIndex] || analyzeSteps[0];
  const safeProgress = Math.max(0, Math.min(progress, 100));

  return (
    <div className="h-[calc(100vh-8rem)] flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between mb-4 flex-shrink-0">
        <div className="flex items-center gap-3">
          {viewMode !== "upload" && (
            <button onClick={resetToUpload} className="flex items-center gap-2 font-body text-fg/60 hover:text-fg transition-colors">
              <ArrowLeft className="w-4 h-4" />
              Quay lại
            </button>
          )}
          <h1 className="font-heading text-3xl text-fg">Rà soát hợp đồng</h1>
        </div>
        <div className="flex items-center gap-2">
          {viewMode === "results" && (
            <button
              onClick={() => setViewMode("history")}
              className="flex items-center gap-2 font-body text-sm text-fg/60 hover:text-fg transition-colors px-3 py-2 border-2 border-fg/20 rounded-lg"
            >
              <Clock className="w-4 h-4" />
              Lịch sử
            </button>
          )}
          {viewMode === "preview" && (
            <WobblyButton onClick={handleAnalyze} size="lg">
              <Eye className="w-5 h-5 mr-2" />
              Rà soát ngay
            </WobblyButton>
          )}
        </div>
      </div>

      {/* Upload Zone */}
      {viewMode === "upload" && (
        <WobblyCard decoration="tape" className="flex-1 flex flex-col items-center justify-center">
          <div className="flex gap-2 mb-6">
            <button
              className={cn(
                "font-body text-lg px-6 py-2 border-2 transition-all",
                inputType === "file" ? "bg-fg text-white border-fg" : "border-fg/30 text-fg/60 hover:border-fg"
              )}
              style={{ borderRadius: "255px 15px 225px 15px / 15px 225px 15px 255px" }}
              onClick={() => setInputType("file")}
            >
              <FileTextIcon className="w-4 h-4 inline mr-2" />
              Tải file
            </button>
            <button
              className={cn(
                "font-body text-lg px-6 py-2 border-2 transition-all",
                inputType === "text" ? "bg-fg text-white border-fg" : "border-fg/30 text-fg/60 hover:border-fg"
              )}
              style={{ borderRadius: "255px 15px 225px 15px / 15px 225px 15px 255px" }}
              onClick={() => setInputType("text")}
            >
              <Type className="w-4 h-4 inline mr-2" />
              Dán văn bản
            </button>
          </div>

          {inputType === "file" ? (
            <div
              className={`border-2 border-dashed border-fg/40 rounded-lg p-16 text-center transition-colors w-full max-w-xl ${
                isDragging ? "bg-muted" : ""
              }`}
              onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
              onDragLeave={() => setIsDragging(false)}
              onDrop={handleDrop}
            >
              <Upload className="w-20 h-20 mx-auto text-fg/30 mb-6" strokeWidth={1.5} />
              <h3 className="font-heading text-3xl text-fg mb-3">Kéo thả hợp đồng vào đây</h3>
              <p className="font-body text-lg text-fg/60 mb-8">Hỗ trợ PDF, DOCX, DOC, TXT, MD — tối đa 10MB</p>
              <input type="file" accept=".pdf,.docx,.doc,.txt,.md" className="hidden" ref={fileInputRef} onChange={handleSelectFile} />
              <WobblyButton size="lg" onClick={() => fileInputRef.current?.click()}>
                Chọn file
              </WobblyButton>
            </div>
          ) : (
            <div className="w-full max-w-2xl">
              <textarea
                className="w-full border-2 border-fg bg-white p-6 font-body text-lg resize-none focus:border-secondary focus:ring-2 focus:ring-secondary/20 focus:outline-none"
                style={{ borderRadius: "12px", minHeight: "300px" }}
                placeholder="Dán nội dung hợp đồng cần rà soát vào đây..."
                value={textContent}
                onChange={(e) => setTextContent(e.target.value)}
              />
              <div className="mt-4 flex justify-between items-center">
                <span className="font-body text-sm text-fg/40">{textContent.length} ký tự</span>
                <WobblyButton size="lg" onClick={handleAnalyze} disabled={!textContent.trim()}>
                  <Eye className="w-5 h-5 mr-2" />
                  Rà soát ngay
                </WobblyButton>
              </div>
            </div>
          )}
        </WobblyCard>
      )}

      {/* Preview */}
      {viewMode === "preview" && (
        <WobblyCard className="flex-1 flex flex-col overflow-hidden">
          <div className="flex items-center gap-3 mb-4 pb-3 border-b border-fg/10">
            <FileText className="w-5 h-5 text-fg/40" />
            <span className="font-body text-lg text-fg">{sourceName}</span>
            {converting && (
              <span className="ml-auto font-body text-sm text-fg/60 flex items-center gap-2">
                <Loader2 className="w-4 h-4 animate-spin" />
                Đang chuyển đổi sang PDF...
              </span>
            )}
          </div>
          <div className="flex-1 overflow-auto bg-muted/30 border-2 border-fg/20 p-4" style={{ borderRadius: "8px" }}>
            {converting ? (
              <div className="flex items-center justify-center h-full">
                <div className="text-center">
                  <Loader2 className="w-12 h-12 animate-spin mx-auto mb-4 text-fg/30" />
                  <p className="font-body text-fg/60">Đang chuyển đổi sang PDF...</p>
                </div>
              </div>
            ) : previewUrl ? (
              <PDFViewer url={previewUrl} />
            ) : (
              <div className="flex items-center justify-center h-full text-fg/40 font-body text-lg">
                Không thể xem trước định dạng này
              </div>
            )}
          </div>
        </WobblyCard>
      )}

      {/* Analyzing Progress */}
      {viewMode === "analyzing" && (
        <WobblyCard decoration="tack" className="flex-1 flex items-center justify-center">
          <div className="text-center max-w-lg w-full">
            <h3 className="font-heading text-2xl text-fg mb-2">Đang phân tích hợp đồng</h3>
            <p className="font-body text-fg/60 mb-8">AI đang đọc và đối chiếu với pháp luật hiện hành...</p>

            <div className="w-full border-2 border-fg bg-white p-1.5 mb-3" style={{ borderRadius: "12px" }}>
              <motion.div
                className="h-5 bg-gradient-to-r from-secondary to-accent"
                style={{ borderRadius: "10px" }}
                animate={{ width: `${safeProgress}%` }}
                transition={{ duration: 0.2 }}
              />
            </div>
            <div className="flex justify-between items-center mb-8">
              <span className="font-body text-lg text-fg">{Math.round(safeProgress)}%</span>
              <span className="font-body text-sm text-fg/60">{currentStep.label}</span>
            </div>

            <div className="space-y-3 text-left">
              {analyzeSteps.map((step, i) => {
                const isDone = currentStatus === "completed" || i < currentStepIndex;
                const isActive = i === currentStepIndex && currentStatus !== "completed";
                return (
                  <div key={step.label} className="flex items-center gap-3">
                    <div className={`w-8 h-8 rounded-full flex items-center justify-center border-2 transition-colors ${
                      isDone ? "bg-secondary text-white border-secondary" :
                      isActive ? "bg-fg text-white border-fg" :
                      "bg-white text-fg/30 border-fg/30"
                    }`} style={{ borderRadius: "50%" }}>
                      {isDone ? <CheckCircle className="w-4 h-4" /> : <div className="w-2 h-2 rounded-full bg-current" />}
                    </div>
                    <span className={`font-body text-lg ${isDone ? "text-secondary" : isActive ? "text-fg" : "text-fg/30"}`}>
                      {step.label}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        </WobblyCard>
      )}

      {/* History View */}
      {viewMode === "history" && (
        <WobblyCard className="flex-1 flex flex-col overflow-hidden">
          <div className="flex items-center gap-3 mb-4 pb-3 border-b border-fg/10">
            <Clock className="w-5 h-5 text-fg/40" />
            <h3 className="font-heading text-lg text-fg">Lịch sử rà soát</h3>
          </div>
          <div className="flex-1 overflow-auto space-y-2">
            {jobHistory.length === 0 ? (
              <div className="text-center py-12 text-fg/40 font-body">
                Chưa có lịch sử rà soát nào
              </div>
            ) : (
              jobHistory.map((job) => (
                <div
                  key={job.id}
                  className="flex items-center gap-3 p-3 border-2 border-fg/10 rounded-lg hover:border-secondary/50 transition-colors cursor-pointer"
                  onClick={() => loadJobResult(job.id)}
                >
                  <FileText className="w-5 h-5 text-fg/40 flex-shrink-0" />
                  <div className="flex-1 min-w-0">
                    <p className="font-body text-sm text-fg truncate">{job.filename}</p>
                    <p className="font-body text-xs text-fg/40">{new Date(job.createdAt).toLocaleString("vi-VN")}</p>
                  </div>
                  {job.documentId && (
                    <button
                      className="p-2 text-fg/40 hover:text-accent transition-colors disabled:opacity-40"
                      disabled={deletingDocumentIds.has(job.documentId)}
                      onClick={(e) => {
                        e.stopPropagation();
                        void handleDeleteDocument(job.documentId!);
                      }}
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  )}
                  <WobblyBadge variant={job.status === "completed" ? "secondary" : job.status === "failed" ? "accent" : "default"}>
                    {job.status === "completed" ? "Hoàn thành" : job.status === "failed" ? "Thất bại" : "Đang xử lý"}
                  </WobblyBadge>
                </div>
              ))
            )}
          </div>
        </WobblyCard>
      )}

      {/* Results: Split View */}
      {viewMode === "results" && (
        <div ref={containerRef} className="flex-1 flex gap-0 overflow-hidden">
          {/* Left: Preview */}
          <div className="overflow-hidden transition-all duration-300" style={{ width: `${splitPosition}%` }}>
            <WobblyCard className="h-full flex flex-col overflow-hidden">
              <div className="flex items-center gap-2 mb-3 pb-2 border-b border-fg/10 flex-shrink-0">
                <Eye className="w-5 h-5 text-secondary" strokeWidth={2.5} />
                <h3 className="font-heading text-lg text-fg">Xem trước</h3>
                <span className="font-body text-sm text-fg/40 ml-auto">{sourceName}</span>
              </div>
              <div className="flex-1 overflow-auto bg-muted/30 border-2 border-fg/20 p-4" style={{ borderRadius: "8px" }}>
                {previewUrl ? (
                  <PDFViewer url={previewUrl} />
                ) : textContent ? (
                  <div
                    className="bg-white p-6 font-body text-fg/80 whitespace-pre-wrap leading-relaxed overflow-auto"
                    style={{ borderRadius: "8px", height: "100%" }}
                    dangerouslySetInnerHTML={{ __html: highlightText(textContent).replace(/\n/g, "<br/>") }}
                  />
                ) : (
                  <div className="flex items-center justify-center h-full text-fg/40 font-body text-lg">
                    Không thể xem trước
                  </div>
                )}
              </div>
            </WobblyCard>
          </div>

          {/* Resizable Divider */}
          <div
            className="w-2 bg-fg/10 hover:bg-secondary/50 cursor-col-resize transition-colors flex-shrink-0"
            onMouseDown={handleMouseDown}
          />

          {/* Right: Results */}
          <div className="overflow-hidden transition-all duration-300" style={{ width: `${100 - splitPosition}%` }}>
            <WobblyCard className="h-full flex flex-col overflow-hidden">
              <div className="flex items-center gap-2 mb-3 pb-2 border-b border-fg/10 flex-shrink-0">
                <FileText className="w-5 h-5 text-accent" strokeWidth={2.5} />
                <h3 className="font-heading text-lg text-fg">Kết quả phân tích</h3>
              </div>

              <div className="flex-1 overflow-auto space-y-6 pr-2 pb-4">
                {snapshotError && (
                  <div className="bg-yellow-50 border-2 border-yellow-300/60 p-3 font-body text-sm text-fg/80" style={{ borderRadius: "12px 4px 12px 4px" }}>
                    {snapshotError}
                  </div>
                )}

                {/* Dashboard / Summary */}
                <div className="grid grid-cols-3 gap-2">
                  <div className="bg-accent/10 border-2 border-accent/20 p-3 flex flex-col items-center justify-center text-center transition-all hover:bg-accent/20" style={{ borderRadius: "255px 15px 225px 15px / 15px 225px 15px 255px" }}>
                    <span className="font-heading text-2xl text-accent">{clauses.filter(c => c.riskLevel === "high").length}</span>
                    <span className="font-body text-xs text-accent">Rủi ro cao</span>
                  </div>
                  <div className="bg-yellow-100/50 border-2 border-yellow-500/20 p-3 flex flex-col items-center justify-center text-center transition-all hover:bg-yellow-100" style={{ borderRadius: "15px 225px 15px 255px / 255px 15px 225px 15px" }}>
                    <span className="font-heading text-2xl text-yellow-600">{clauses.filter(c => c.riskLevel === "medium").length}</span>
                    <span className="font-body text-xs text-yellow-600">Cần xem xét</span>
                  </div>
                  <div className="bg-green-100/50 border-2 border-green-500/20 p-3 flex flex-col items-center justify-center text-center transition-all hover:bg-green-100" style={{ borderRadius: "225px 15px 255px 15px / 15px 255px 15px 225px" }}>
                    <span className="font-heading text-2xl text-green-600">{clauses.filter(c => c.riskLevel === "low").length}</span>
                    <span className="font-body text-xs text-green-600">An toàn</span>
                  </div>
                </div>

                {/* Violations / Risks Found */}
                {compliance?.violations && compliance.violations.length > 0 && (
                  <div>
                    <h4 className="font-heading text-lg text-accent mb-2 flex items-center gap-2 mt-4">
                      <AlertTriangle className="w-5 h-5" />
                      {compliance.violations.length} rủi ro được tìm thấy
                    </h4>
                    <div className="space-y-2">
                      {compliance.violations.map((v, i) => (
                        <div
                          key={i}
                          className="bg-accent/10 border-2 border-accent/30 p-3 cursor-pointer hover:bg-accent/20 transition-colors"
                          style={{ borderRadius: "60px 4px 45px 4px / 4px 45px 4px 60px" }}
                          onClick={() => {
                            setHighlightedClauseId(highlightedClauseId === v.contractClauseId ? null : v.contractClauseId || null);
                            if (v.contractClauseId && !expandedClauses.has(v.contractClauseId)) {
                              toggleClause(v.contractClauseId);
                            }
                          }}
                        >
                          <div className="flex items-start gap-2">
                            <span className="font-heading text-accent text-sm flex-shrink-0 mt-0.5">#{i + 1}</span>
                            <div className="flex-1">
                              <h5 className="font-heading text-fg text-sm mb-1">{v.clause}</h5>
                              <p className="font-body text-sm text-fg/80">{v.description}</p>
                              {v.citation && <p className="mt-1 font-body text-xs text-fg/50 italic">Nguồn: {v.citation}</p>}
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Legal Documents Sources */}
                {uniqueDocuments.length > 0 && (
                  <div className="mt-4">
                    <h4 className="font-heading text-lg text-fg mb-2 flex items-center gap-2">
                      <BookOpen className="w-5 h-5" />
                      Văn bản pháp luật tham chiếu ({uniqueDocuments.length})
                    </h4>
                    <div className="space-y-2">
                      {uniqueDocuments.map((doc, i) => (
                        <button
                          key={i}
                          className="w-full text-left bg-white border-2 border-fg/10 p-3 hover:border-secondary/50 hover:bg-secondary/5 transition-colors"
                          style={{ borderRadius: "60px 4px 45px 4px / 4px 45px 4px 60px" }}
                          onClick={() => loadDocumentContent(doc.title)}
                        >
                          <div className="flex items-center gap-2">
                            <FileText className="w-4 h-4 text-secondary flex-shrink-0" />
                            <span className="font-body text-sm text-fg/80">{doc.title}</span>
                            <WobblyBadge variant="secondary" className="ml-auto">{doc.citations.length} điều</WobblyBadge>
                          </div>
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {/* All Clauses */}
                <div className="mt-4">
                  <h4 className="font-heading text-lg text-fg mb-3 flex items-center gap-2">
                    <FileText className="w-5 h-5" />
                    Chi tiết từng điều khoản ({clauses.length})
                  </h4>
                  <div className="space-y-3">
                    {clauses.map((clause) => {
                      const clauseViolations = compliance?.violations?.filter(v => v.contractClauseId === clause.id || v.contractClauseType === clause.type) || [];
                      const matches = legalMatches.filter((match) => match.clauseId === clause.id).slice(0, 3);
                      
                      const words = clause.text.split(" ");
                      const titleSnippet = words.slice(0, 15).join(" ") + (words.length > 15 ? "..." : "");

                      return (
                        <div
                          key={clause.id}
                          className={`border-2 p-3 cursor-pointer transition-all ${riskColor(clause.riskLevel)}`}
                          style={{ borderRadius: "60px 4px 45px 4px / 4px 45px 4px 60px" }}
                          onClick={() => toggleClause(clause.id)}
                        >
                          <div className="flex items-center justify-between gap-3">
                            <div className="flex items-center gap-2 flex-1 min-w-0">
                              {expandedClauses.has(clause.id) ? <ChevronDown className="w-4 h-4 flex-shrink-0" /> : <ChevronRight className="w-4 h-4 flex-shrink-0" />}
                              <span className="font-body text-sm font-semibold flex-1 truncate">{titleSnippet}</span>
                            </div>
                            <WobblyBadge variant={clause.riskLevel === "low" ? "secondary" : clause.riskLevel === "medium" ? "postit" : "accent"} className="flex-shrink-0">
                              {clause.riskLevel === "low" ? "Thấp" : clause.riskLevel === "medium" ? "Trung bình" : "Cao"}
                            </WobblyBadge>
                          </div>
                          
                          <AnimatePresence>
                            {expandedClauses.has(clause.id) && (
                              <motion.div className="mt-3 pt-3 border-t border-current/20 space-y-4 text-sm cursor-default" onClick={(e) => e.stopPropagation()} initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }}>
                                
                                {/* 1. Nội dung chi tiết */}
                                <div>
                                  <h5 className="font-heading text-xs uppercase tracking-wider opacity-70 mb-1">Nội dung hợp đồng</h5>
                                  <p className="font-body opacity-90 leading-relaxed bg-white/50 p-3 border border-current/10 whitespace-pre-wrap" style={{ borderRadius: "60px 4px 45px 4px / 4px 45px 4px 60px" }}>{clause.text}</p>
                                </div>

                                {/* 2. Phân tích rủi ro */}
                                {(clauseViolations.length > 0 || clause.riskLevel !== "low") && (
                                  <div>
                                    <h5 className={`font-heading text-xs uppercase tracking-wider mb-2 flex items-center gap-1 ${clause.riskLevel === "high" ? "text-accent" : "text-yellow-700"}`}>
                                      <AlertTriangle className="w-4 h-4" /> Cảnh báo rủi ro
                                    </h5>
                                    {clauseViolations.length > 0 ? (
                                      <div className="space-y-2">
                                        {clauseViolations.map((v, i) => (
                                          <div key={i} className="bg-white/60 p-3 font-body text-sm border border-current/10" style={{ borderRadius: "30px 4px 25px 4px / 4px 25px 4px 30px" }}>
                                            <span className="font-semibold">{v.description}</span>
                                            {v.citation && <p className="text-xs mt-1.5 pt-1.5 border-t border-current/10 opacity-80">Nguồn đối chiếu: <span className="font-semibold">{v.citation}</span></p>}
                                          </div>
                                        ))}
                                      </div>
                                    ) : (
                                      <div className="bg-white/60 p-3 font-body text-sm border border-current/10" style={{ borderRadius: "30px 4px 25px 4px / 4px 25px 4px 30px" }}>
                                        {clause.riskLevel === "high" ? "Điều khoản này chứa rủi ro cao hoặc có dấu hiệu vi phạm quy định pháp luật." : "Điều khoản này cần được xem xét lại để tránh bất lợi."}
                                      </div>
                                    )}
                                  </div>
                                )}

                                {/* 3. Gợi ý sửa đổi & Citations */}

                                {(matches.length > 0) && (
                                  <div>
                                    <h5 className="font-heading text-xs uppercase tracking-wider opacity-70 mb-2 flex items-center gap-1">
                                      <CheckCircle className="w-3 h-3" /> Gợi ý & Căn cứ pháp lý
                                    </h5>
                                    <div className="space-y-2">
                                      {matches.map((match) => {
                                        const matchKey = `${clause.id}:${match.uid}`;
                                        const isMatchExpanded = expandedMatches.has(matchKey);
                                        const matchText = match.text?.trim();

                                        return (
                                          <button
                                            key={matchKey}
                                            type="button"
                                            className="w-full text-left bg-white/70 border border-fg/10 p-2 hover:bg-white transition-colors"
                                            style={{ borderRadius: "30px 4px 25px 4px / 4px 25px 4px 30px" }}
                                            onClick={() => toggleMatch(matchKey)}
                                          >
                                            <div className="flex items-start gap-2">
                                              <WobblyBadge variant="secondary" className="mt-0.5 whitespace-nowrap">{match.segmentType}</WobblyBadge>
                                              <div className="flex-1 min-w-0">
                                                <span className="font-body font-semibold text-xs text-fg block truncate" title={match.citation}>{match.citation}</span>
                                              </div>
                                              {isMatchExpanded ? <ChevronDown className="w-4 h-4 text-fg/40 flex-shrink-0" /> : <ChevronRight className="w-4 h-4 text-fg/40 flex-shrink-0" />}
                                            </div>

                                            <AnimatePresence initial={false}>
                                              {isMatchExpanded && (
                                                <motion.div
                                                  className="mt-2 border-t border-fg/10 pt-2 font-body text-xs text-fg/70 leading-relaxed whitespace-pre-wrap"
                                                  initial={{ height: 0, opacity: 0 }}
                                                  animate={{ height: "auto", opacity: 1 }}
                                                  exit={{ height: 0, opacity: 0 }}
                                                >
                                                  {matchText || "Snapshot cũ chưa có nội dung điều luật. Chạy rà soát lại để tải nội dung thật từ Neo4j."}
                                                  {match.validitySignal !== "latest_known" && (
                                                    <div className="mt-2 text-[10px] uppercase tracking-wider text-fg/40">{match.validitySignal}</div>
                                                  )}
                                                </motion.div>
                                              )}
                                            </AnimatePresence>
                                          </button>
                                        );
                                      })}
                                    </div>
                                  </div>
                                )}
                              </motion.div>
                            )}
                          </AnimatePresence>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>
            </WobblyCard>
          </div>
        </div>
      )}

      {/* Document Viewer Modal */}
      <AnimatePresence>
        {selectedDocument && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4"
            onClick={() => setSelectedDocument(null)}
          >
            <motion.div
              initial={{ scale: 0.9, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.9, opacity: 0 }}
              className="bg-white rounded-lg max-w-4xl w-full max-h-[90vh] overflow-hidden flex flex-col"
              onClick={(e) => e.stopPropagation()}
            >
              {/* Header */}
              <div className="flex items-center justify-between p-4 border-b border-fg/10 flex-shrink-0">
                <div>
                  <h3 className="font-heading text-lg text-fg">{selectedDocument.title}</h3>
                  <p className="font-body text-xs text-fg/50">
                    {selectedDocument.so_ky_hieu} • {selectedDocument.ngay_ban_hanh} • {selectedDocument.co_quan_ban_hanh}
                  </p>
                </div>
                <button
                  className="p-2 hover:bg-fg/10 rounded-full transition-colors"
                  onClick={() => setSelectedDocument(null)}
                >
                  <X className="w-5 h-5" />
                </button>
              </div>

              {/* Content */}
              <div className="flex-1 overflow-auto p-6">
                {documentLoading ? (
                  <div className="flex items-center justify-center h-32">
                    <Loader2 className="w-8 h-8 animate-spin text-fg/30" />
                  </div>
                ) : (
                  <div className="space-y-6">
                    {selectedDocument.articles.map((article) => (
                      <div key={article.uid} className="border-b border-fg/10 pb-4 last:border-0">
                        <h4 className="font-heading text-base text-fg mb-2">
                          {article.title}
                        </h4>
                        <p className="font-body text-sm text-fg/70 whitespace-pre-wrap mb-3">
                          {article.text}
                        </p>
                        {article.clauses.length > 0 && (
                          <div className="ml-4 space-y-2">
                            {article.clauses.map((clause) => (
                              <div key={clause.uid}>
                                <p className="font-body text-sm text-fg/70 whitespace-pre-wrap">
                                  {clause.text}
                                </p>
                                {clause.points.length > 0 && (
                                  <div className="ml-4 mt-1 space-y-1">
                                    {clause.points.map((point) => (
                                      <p key={point.uid} className="font-body text-sm text-fg/70 whitespace-pre-wrap">
                                        {point.letter ? `${point.letter} ` : ""}{point.text}
                                      </p>
                                    ))}
                                  </div>
                                )}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
