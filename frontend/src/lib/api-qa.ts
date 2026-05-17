import { apiRequest, apiSSE } from "./api-client";
import type { Message, IntentResult, Provision, Citation } from "./mock-api-qa";

export interface ChatRequest {
  message: string;
  conversationId?: string;
  tabId?: string;
}

export interface ChatChunk {
  token: string;
  conversationId?: string;
  intents?: IntentResult[];
  provisions?: Provision[];
  citations?: Citation[];
  done?: boolean;
}

export interface ChatResponse {
  messageId: string;
  content: string;
  intents: IntentResult[];
  provisions: Provision[];
}

export interface ConversationSummary {
  id: string;
  title: string;
  lastMessage: string;
  createdAt: string;
  lastMessageAt?: string | null;
  tabId?: string | null;
}

export interface ConversationDetail {
  id: string;
  title: string;
  createdAt: string;
  lastMessageAt?: string | null;
  messages: Message[];
}

export async function sendMessage(
  conversationId: string | null,
  tabId: string,
  content: string,
  onToken: (token: string) => void,
  onConversationId?: (conversationId: string) => void,
  onMetadata?: (metadata: { intents?: IntentResult[]; provisions?: Provision[] }) => void
): Promise<{ conversationId: string; message: Message }> {
  let fullContent = "";
  let intents: IntentResult[] = [];
  let provisions: Provision[] = [];
  let citations: Citation[] = [];
  let createdConversationId = conversationId || "";

  await apiSSE<ChatChunk>(
    "/api/qa/chat",
    { message: content, conversationId: conversationId || undefined, tabId },
    (chunk) => {
      if (chunk.conversationId) {
        createdConversationId = chunk.conversationId;
        onConversationId?.(chunk.conversationId);
      }
      if (chunk.token) {
        fullContent += chunk.token;
        onToken(chunk.token);
      }
      if (chunk.intents) {
        intents = chunk.intents;
        onMetadata?.({ intents });
      }
      if (chunk.provisions) {
        provisions = chunk.provisions;
        onMetadata?.({ provisions });
      }
      if (chunk.citations) {
        citations = chunk.citations;
      }
    }
  );

  return {
    conversationId: createdConversationId,
    message: {
      id: `msg_${Date.now()}`,
      role: "assistant",
      content: fullContent,
      intents,
      provisions,
      citations,
      timestamp: new Date().toISOString(),
    },
  };
}

export async function createConversation(tabId: string): Promise<{ id: string }> {
  return apiRequest<{ id: string }>("/api/qa/conversations", {
    method: "POST",
    body: JSON.stringify({ title: "New conversation", tabId }),
  });
}

export async function getConversations(): Promise<ConversationSummary[]> {
  return apiRequest<ConversationSummary[]>("/api/qa/conversations");
}

export async function getConversation(id: string): Promise<ConversationDetail> {
  return apiRequest<ConversationDetail>(`/api/qa/conversations/${id}`);
}

export async function getTabConversation(tabId: string): Promise<ConversationDetail | null> {
  try {
    return await apiRequest<ConversationDetail>(`/api/qa/conversations/tab/${tabId}`, {}, { retries: 0 });
  } catch (error: any) {
    if (error?.status === 404) return null;
    throw error;
  }
}

export async function renameConversation(id: string, title: string): Promise<ConversationSummary> {
  return apiRequest<ConversationSummary>(`/api/qa/conversations/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ title }),
  });
}

export async function deleteConversation(id: string): Promise<void> {
  await apiRequest(`/api/qa/conversations/${id}`, { method: "DELETE" });
}
