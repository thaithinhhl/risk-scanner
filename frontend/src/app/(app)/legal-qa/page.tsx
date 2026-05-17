"use client";

import { useState, useRef, useEffect } from "react";
import { useSearchParams } from "next/navigation";
import { WobblyButton } from "@/components/ui/wobbly-button";
import { WobblyCard } from "@/components/ui/wobbly-card";
import { ChatBubble } from "@/components/qa/chat-bubble";
import { qaApi } from "@/lib/api";
import { getLegalQaTabId, resetLegalQaTabId } from "@/lib/chat-tab";
import type { Message } from "@/lib/mock-api-qa";
import { Send, Plus, MessageSquare } from "lucide-react";

export default function LegalQAPage() {
  const searchParams = useSearchParams();
  const [mounted, setMounted] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [tabId, setTabId] = useState<string>("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingContent, setStreamingContent] = useState("");
  const [streamingIntents, setStreamingIntents] = useState<any[]>([]);
  const [streamingProvisions, setStreamingProvisions] = useState<any[]>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingContent, isStreaming]);

  useEffect(() => {
    setMounted(true);
    const currentTabId = getLegalQaTabId();
    setTabId(currentTabId);

    const restore = async () => {
      try {
        const tabConversation = await qaApi.getTabConversation(currentTabId);
        if (tabConversation) {
          setConversationId(tabConversation.id);
          setMessages(tabConversation.messages);
        }
      } catch (error) {
        console.error("Could not restore QA conversation:", error);
      }
    };

    restore();
  }, []);

  useEffect(() => {
    const id = searchParams.get("conversationId");
    if (!id || id === conversationId || isStreaming) return;

    const loadFromUrl = async () => {
      try {
        const conversation = await qaApi.getConversation(id);
        setConversationId(conversation.id);
        setMessages(conversation.messages);
      } catch (error) {
        console.error("Could not load conversation from URL:", error);
      }
    };

    loadFromUrl();
  }, [conversationId, isStreaming, searchParams]);

  const notifyHistoryChanged = () => {
    window.dispatchEvent(new Event("legal-qa:history-changed"));
  };

  const handleSend = async () => {
    if (!mounted || !input.trim() || isStreaming || !tabId) return;

    const userMessage: Message = {
      id: `msg_${Date.now()}`,
      role: "user",
      content: input,
      timestamp: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, userMessage]);

    const question = input;
    setInput("");
    setIsStreaming(true);
    setStreamingContent("");
    setStreamingIntents([]);
    setStreamingProvisions([]);

    try {
      const result = await qaApi.sendMessage(
        conversationId,
        tabId,
        question,
        (token) => {
          setStreamingContent((prev) => prev + token);
        },
        (newConversationId) => {
          setConversationId(newConversationId);
        },
        (metadata) => {
          if (metadata.intents) setStreamingIntents(metadata.intents);
          if (metadata.provisions) setStreamingProvisions(metadata.provisions);
        }
      );

      setConversationId(result.conversationId);
      setMessages((prev) => [...prev, result.message]);
      notifyHistoryChanged();
    } catch (err) {
      console.error("QA error:", err);
      setMessages((prev) => [
        ...prev,
        {
          id: `msg_err_${Date.now()}`,
          role: "assistant",
          content: "Có lỗi xảy ra khi trả lời. Vui lòng thử lại.",
          timestamp: new Date().toISOString(),
        },
      ]);
    }

    setIsStreaming(false);
    setStreamingContent("");
  };

  const handleNewConversation = () => {
    const nextTabId = resetLegalQaTabId();
    setTabId(nextTabId);
    setConversationId(null);
    setMessages([]);
    setStreamingContent("");
    setIsStreaming(false);
    notifyHistoryChanged();
  };

  return (
    <div className="flex flex-col h-[calc(100vh-8rem)]">
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <MessageSquare className="w-6 h-6 text-secondary" strokeWidth={2.5} />
            <h1 className="font-heading text-3xl text-fg">Hỏi đáp pháp lý</h1>
          </div>
          <WobblyButton variant="secondary" size="sm" onClick={handleNewConversation} disabled={mounted ? isStreaming : undefined}>
            <Plus className="w-4 h-4 mr-2" />
            Mới
          </WobblyButton>
        </div>

        {/* Messages */}
        <WobblyCard className="flex-1 overflow-y-auto mb-4">
          {messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-center">
              <MessageSquare className="w-16 h-16 text-fg/20 mb-4" strokeWidth={1.5} />
              <h3 className="font-heading text-2xl text-fg mb-2">Hỏi đáp pháp lý</h3>
              <p className="font-body text-fg/60 max-w-md">
                Đặt câu hỏi về pháp luật Việt Nam. AI sẽ phân tích và trả lời kèm trích dẫn văn bản pháp lý.
              </p>
              <div className="mt-6 flex flex-wrap gap-2 justify-center">
                {[
                  "Lương tối thiểu vùng I",
                  "Nội dung điều 1 bộ luật Lao động",
                ].map((q) => (
                  <button
                    key={q}
                    className="font-body text-sm text-secondary border border-secondary/30 px-3 py-2 hover:bg-secondary/10 transition-colors"
                    style={{ borderRadius: "60px 4px 45px 4px / 4px 45px 4px 60px" }}
                    onClick={() => { setInput(q); }}
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="space-y-6">
              {messages.map((msg) => (
                <ChatBubble key={msg.id} message={msg} />
              ))}
              {isStreaming && (
                <ChatBubble
                  message={{
                    id: "streaming",
                    role: "assistant",
                    content: streamingContent || "Đang trả lời...",
                    timestamp: new Date().toISOString(),
                    intents: streamingIntents,
                    provisions: streamingProvisions,
                  }}
                  isStreaming
                />
              )}
              <div ref={messagesEndRef} />
            </div>
          )}
        </WobblyCard>

        {/* Input */}
        <div className="flex gap-3">
          <input
            className="flex-1 font-body text-lg border-2 border-fg bg-white px-4 py-3 focus:border-secondary focus:ring-2 focus:ring-secondary/20 focus:outline-none"
            style={{ borderRadius: "120px 8px 90px 8px / 8px 90px 8px 120px" }}
            placeholder="Nhập câu hỏi pháp lý..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleSend()}
            disabled={mounted ? isStreaming : undefined}
          />
          <WobblyButton onClick={handleSend} disabled={mounted ? (isStreaming || !input.trim() || !tabId) : undefined}>
            <Send className="w-5 h-5" />
          </WobblyButton>
        </div>
    </div>
  );
}
