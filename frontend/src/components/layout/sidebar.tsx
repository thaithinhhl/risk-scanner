"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { useLogoutConfirm } from "@/lib/logout-context";
import { contractApi, qaApi } from "@/lib/api";
import type { ContractJob } from "@/lib/api-contract";
import type { Conversation } from "@/lib/mock-api-qa";
import {
  FileText,
  MessageSquare,
  LayoutDashboard,
  Settings,
  Zap,
  LogOut,
  ChevronDown,
  ChevronUp,
  Edit3,
  Check,
  X,
  Trash2,
} from "lucide-react";

const navItems = [
  { href: "/dashboard", label: "Tổng quan", icon: LayoutDashboard },
  { href: "/contract-review", label: "Rà soát hợp đồng", icon: FileText },
  { href: "/legal-qa", label: "Hỏi đáp pháp lý", icon: MessageSquare },
  { href: "/settings", label: "Cài đặt", icon: Settings },
  { href: "/upgrade", label: "Nâng cấp", icon: Zap },
];

interface SidebarProps {
  collapsed: boolean;
  onToggle: () => void;
}

export function Sidebar({ collapsed, onToggle }: SidebarProps) {
  const pathname = usePathname();
  const [hoveredItem, setHoveredItem] = useState<string | null>(null);
  const [showContractHistory, setShowContractHistory] = useState(true);
  const [showQaHistory, setShowQaHistory] = useState(true);
  const [contractJobs, setContractJobs] = useState<ContractJob[]>([]);
  const [qaConversations, setQaConversations] = useState<Conversation[]>([]);
  const [deletingContractIds, setDeletingContractIds] = useState<Set<string>>(new Set());
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingTitle, setEditingTitle] = useState("");
  const { showLogoutConfirm } = useLogoutConfirm();
  const isContractReview = pathname === "/contract-review";
  const isLegalQa = pathname === "/legal-qa";

  const loadContractHistory = async () => {
    if (collapsed || !isContractReview) return;
    try {
      const history = await contractApi.getJobHistory();
      setContractJobs(history as ContractJob[]);
    } catch (error) {
      console.error("Could not load contract review history:", error);
    }
  };

  const loadQaHistory = async () => {
    if (collapsed || !isLegalQa) return;
    try {
      const history = await qaApi.getConversations();
      setQaConversations(history as Conversation[]);
    } catch (error) {
      console.error("Could not load QA history:", error);
    }
  };

  useEffect(() => {
    loadContractHistory();
    loadQaHistory();
  }, [collapsed, isContractReview, isLegalQa]);

  useEffect(() => {
    const onHistoryChanged = () => loadQaHistory();
    window.addEventListener("legal-qa:history-changed", onHistoryChanged);
    return () => window.removeEventListener("legal-qa:history-changed", onHistoryChanged);
  }, [collapsed, isLegalQa]);

  useEffect(() => {
    const onHistoryChanged = () => loadContractHistory();
    window.addEventListener("contract-review:history-changed", onHistoryChanged);
    return () => window.removeEventListener("contract-review:history-changed", onHistoryChanged);
  }, [collapsed, isContractReview]);

  const startRename = (conversation: Conversation) => {
    setEditingId(conversation.id);
    setEditingTitle(conversation.title);
  };

  const saveRename = async () => {
    if (!editingId || !editingTitle.trim()) return;
    try {
      await qaApi.renameConversation(editingId, editingTitle.trim());
      setEditingId(null);
      setEditingTitle("");
      await loadQaHistory();
    } catch (error) {
      console.error("Could not rename QA conversation:", error);
    }
  };

  const deleteConversation = async (id: string) => {
    try {
      await qaApi.deleteConversation(id);
      await loadQaHistory();
      window.dispatchEvent(new Event("legal-qa:history-changed"));
    } catch (error) {
      console.error("Could not delete QA conversation:", error);
    }
  };

  const deleteContractDocument = async (job: ContractJob) => {
    if (!job.documentId) return;
    if (deletingContractIds.has(job.documentId)) return;

    const previousJobs = contractJobs;
    setDeletingContractIds((prev) => new Set(prev).add(job.documentId!));
    setContractJobs((prev) => prev.filter((item) => item.documentId !== job.documentId));
    window.dispatchEvent(new Event("contract-review:history-changed"));

    try {
      await contractApi.deleteDocument(job.documentId);
    } catch (error) {
      console.error("Could not delete contract document:", error);
      setContractJobs(previousJobs);
    } finally {
      setDeletingContractIds((prev) => {
        const next = new Set(prev);
        next.delete(job.documentId!);
        return next;
      });
    }
  };

  const renderContractHistory = () => {
    if (collapsed || !isContractReview || !showContractHistory || contractJobs.length === 0) return null;

    return (
      <div className="mt-1 mb-1 max-h-[22.5rem] overflow-y-auto space-y-2 px-1 pr-1">
        {contractJobs.map((job) => (
          <div
            key={job.id}
            className="border-2 border-fg/20 bg-white p-2"
            style={{ borderRadius: "30px 4px 25px 4px / 4px 25px 4px 30px" }}
          >
            <div className="flex items-start gap-2">
              <Link
                href={`/contract-review?jobId=${encodeURIComponent(job.id)}`}
                className="min-w-0 flex-1 font-heading text-sm text-fg hover:text-secondary"
              >
                <span className="block truncate">{job.filename}</span>
              </Link>
              {job.documentId && (
                <button
                  onClick={(event) => {
                    event.preventDefault();
                    event.stopPropagation();
                    void deleteContractDocument(job);
                  }}
                  disabled={deletingContractIds.has(job.documentId)}
                  className="shrink-0 text-fg/60 hover:text-red-600 disabled:opacity-40"
                  aria-label="Xóa"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              )}
            </div>
            <div className="mt-1 flex items-center gap-2">
              <span className="font-body text-xs text-fg/60 truncate">
                {new Date(job.createdAt).toLocaleDateString("vi-VN")}
              </span>
              <span className={cn(
                "font-body text-xs",
                job.status === "completed" ? "text-secondary" : job.status === "failed" ? "text-red-600" : "text-fg/60"
              )}>
                {job.status === "completed" ? "Hoàn thành" : job.status === "failed" ? "Thất bại" : "Đang xử lý"}
              </span>
            </div>
          </div>
        ))}
      </div>
    );
  };

  const renderQaHistory = () => {
    if (collapsed || !isLegalQa || !showQaHistory || qaConversations.length === 0) return null;

    return (
      <div className="mt-1 mb-1 max-h-[22.5rem] overflow-y-auto space-y-2 px-1 pr-1">
        {qaConversations.map((conv) => (
          <div
            key={conv.id}
            className="border-2 border-fg/20 bg-white p-2"
            style={{ borderRadius: "30px 4px 25px 4px / 4px 25px 4px 30px" }}
          >
            {editingId === conv.id ? (
              <div className="flex items-center gap-1">
                <input
                  className="min-w-0 flex-1 border border-fg/30 px-2 py-1 font-body text-xs"
                  value={editingTitle}
                  onChange={(event) => setEditingTitle(event.target.value)}
                  onKeyDown={(event) => event.key === "Enter" && saveRename()}
                />
                <button onClick={saveRename} className="text-secondary" aria-label="Lưu tên">
                  <Check className="w-4 h-4" />
                </button>
                <button onClick={() => setEditingId(null)} className="text-fg/60" aria-label="Hủy đổi tên">
                  <X className="w-4 h-4" />
                </button>
              </div>
            ) : (
              <>
                <div className="flex items-start gap-2">
                  <Link
                    href={`/legal-qa?conversationId=${encodeURIComponent(conv.id)}`}
                    className="min-w-0 flex-1 font-heading text-sm text-fg hover:text-secondary"
                  >
                    <span className="block truncate">{conv.title}</span>
                  </Link>
                  <div className="flex shrink-0 gap-1">
                    <button onClick={() => startRename(conv)} className="text-fg/60 hover:text-secondary" aria-label="Đổi tên">
                      <Edit3 className="w-4 h-4" />
                    </button>
                    <button onClick={() => deleteConversation(conv.id)} className="text-fg/60 hover:text-red-600" aria-label="Xóa">
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
                <p className="font-body text-xs text-fg/60 truncate mt-1">{conv.lastMessage}</p>
              </>
            )}
          </div>
        ))}
      </div>
    );
  };

  return (
    <aside
      className={cn(
        "h-screen border-r-2 border-fg bg-white/90 backdrop-blur-sm flex flex-col relative overflow-hidden transition-[width] duration-300 ease-in-out",
        collapsed ? "w-16" : "w-64"
      )}
    >
      {/* Logo / Toggle */}
      <div
        className={cn(
          "flex items-center border-r-2 border-fg/20 h-16 transition-all duration-300",
          collapsed ? "justify-center px-2" : "justify-between px-4"
        )}
      >
        <div
          className={cn(
            "overflow-hidden transition-all duration-300 ease-in-out whitespace-nowrap",
            collapsed ? "w-0 opacity-0" : "w-auto opacity-100"
          )}
        >
          <Link href="/" className="font-heading text-2xl text-fg hover:text-accent transition-colors">
            PhápLý
          </Link>
        </div>
        <button
          onClick={onToggle}
          className={cn(
            "flex items-center justify-center w-8 h-8 border-2 border-fg/30 hover:border-fg hover:bg-muted transition-all duration-200 flex-shrink-0",
            !collapsed && "ml-auto"
          )}
          style={{ borderRadius: "255px 15px 225px 15px / 15px 225px 15px 255px" }}
        >
          <svg
            className={cn("w-4 h-4 text-fg transition-transform duration-300", collapsed && "rotate-180")}
            viewBox="0 0 16 16"
            fill="none"
          >
            <path d="M10 3 L5 8 L10 13" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      </div>

      {/* Nav Items */}
      <nav className="flex-1 py-4 space-y-1 px-2 overflow-hidden">
        {navItems.map(({ href, label, icon: Icon }) => {
          const isActive = pathname === href;
          return (
            <div
              key={href}
              className="relative"
              onMouseEnter={() => collapsed && setHoveredItem(href)}
              onMouseLeave={() => setHoveredItem(null)}
            >
              <div className="flex items-stretch">
                <Link
                  href={href}
                  className={cn(
                    "flex min-w-0 flex-1 items-center py-3 overflow-hidden transition-all duration-300 ease-in-out",
                    collapsed ? "justify-center px-0" : "px-4 gap-3",
                    isActive ? "bg-fg text-white" : "text-fg hover:bg-muted"
                  )}
                  style={{
                    borderRadius:
                      (href === "/legal-qa" || href === "/contract-review") && !collapsed
                        ? "255px 15px 15px 255px / 15px 225px 225px 15px"
                        : "255px 15px 225px 15px / 15px 225px 15px 255px",
                  }}
                >
                  <Icon className="w-5 h-5 flex-shrink-0" strokeWidth={2.5} />
                  <span
                    className={cn(
                      "font-body text-lg whitespace-nowrap transition-all duration-300 ease-in-out",
                      collapsed ? "w-0 opacity-0 ml-0" : "w-auto opacity-100 ml-0"
                    )}
                  >
                    {label}
                  </span>
                </Link>
                {href === "/contract-review" && !collapsed && (
                  <button
                    type="button"
                    onClick={() => setShowContractHistory((value) => !value)}
                    className={cn(
                      "flex w-10 items-center justify-center transition-colors duration-300",
                      isActive ? "bg-fg text-white" : "text-fg hover:bg-muted"
                    )}
                    style={{ borderRadius: "15px 255px 255px 15px / 225px 15px 15px 225px" }}
                    aria-label={showContractHistory ? "Ẩn lịch sử rà soát" : "Hiện lịch sử rà soát"}
                  >
                    {showContractHistory ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                  </button>
                )}
                {href === "/legal-qa" && !collapsed && (
                  <button
                    type="button"
                    onClick={() => setShowQaHistory((value) => !value)}
                    className={cn(
                      "flex w-10 items-center justify-center transition-colors duration-300",
                      isActive ? "bg-fg text-white" : "text-fg hover:bg-muted"
                    )}
                    style={{ borderRadius: "15px 255px 255px 15px / 225px 15px 15px 225px" }}
                    aria-label={showQaHistory ? "Ẩn lịch sử hỏi đáp" : "Hiện lịch sử hỏi đáp"}
                  >
                    {showQaHistory ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                  </button>
                )}
              </div>
              {href === "/contract-review" && renderContractHistory()}
              {href === "/legal-qa" && renderQaHistory()}
              {collapsed && hoveredItem === href && (
                <div className="absolute left-full top-1/2 -translate-y-1/2 ml-2 px-3 py-1.5 bg-fg text-white font-body text-sm whitespace-nowrap z-50 pointer-events-none">
                  {label}
                  <div className="absolute left-0 top-1/2 -translate-y-1/2 -translate-x-1 w-2 h-2 bg-fg rotate-45" />
                </div>
              )}
            </div>
          );
        })}
      </nav>

      {/* Logout */}
      <div className="p-2 border-t-2 border-fg/20">
        <div
          className="relative"
          onMouseEnter={() => collapsed && setHoveredItem("logout")}
          onMouseLeave={() => setHoveredItem(null)}
        >
          <button
            onClick={showLogoutConfirm}
            className={cn(
              "flex items-center py-3 overflow-hidden transition-all duration-300 ease-in-out w-full",
              collapsed ? "justify-center px-0" : "px-4 gap-3",
              "text-fg/60 hover:text-accent hover:bg-muted/50"
            )}
            style={{ borderRadius: "255px 15px 225px 15px / 15px 225px 15px 255px" }}
          >
            <LogOut className="w-5 h-5 flex-shrink-0" strokeWidth={2.5} />
            <span
              className={cn(
                "font-body text-lg whitespace-nowrap transition-all duration-300 ease-in-out",
                collapsed ? "w-0 opacity-0 ml-0" : "w-auto opacity-100 ml-0"
              )}
            >
              Đăng xuất
            </span>
          </button>
          {collapsed && hoveredItem === "logout" && (
            <div className="absolute left-full top-1/2 -translate-y-1/2 ml-2 px-3 py-1.5 bg-fg text-white font-body text-sm whitespace-nowrap z-50 pointer-events-none">
              Đăng xuất
              <div className="absolute left-0 top-1/2 -translate-y-1/2 -translate-x-1 w-2 h-2 bg-fg rotate-45" />
            </div>
          )}
        </div>
      </div>
    </aside>
  );
}
