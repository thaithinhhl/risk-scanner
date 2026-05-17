"use client";

import { createContext, useContext, useEffect, useState, useCallback, ReactNode } from "react";
import { useRouter, usePathname } from "next/navigation";
import "@/lib/fetch-interceptor";

const CHANNEL_NAME = "auth-sync";
const SESSION_CHECK_INTERVAL = 5 * 60 * 1000; // 5 minutes
const LOGOUT_INITIATOR_KEY = "auth-sync:logout-initiator";

type AuthEventType = "login" | "logout" | "session-expired";

interface AuthSyncContextType {
  broadcastLogin: () => void;
  broadcastLogout: () => void;
  broadcastSessionExpired: () => void;
}

const AuthSyncContext = createContext<AuthSyncContextType>({
  broadcastLogin: () => {},
  broadcastLogout: () => {},
  broadcastSessionExpired: () => {},
});

export function useAuthSync() {
  return useContext(AuthSyncContext);
}

// Broadcast functions (can be called from anywhere)
let channel: BroadcastChannel | null = null;

function getChannel(): BroadcastChannel {
  if (!channel && typeof window !== "undefined") {
    channel = new BroadcastChannel(CHANNEL_NAME);
  }
  return channel!;
}

export function broadcastLogin() {
  try {
    getChannel().postMessage({ type: "login" });
  } catch {}
}

export function broadcastLogout() {
  try {
    // Mark this tab as the logout initiator so it doesn't show the modal
    if (typeof window !== "undefined") {
      sessionStorage.setItem(LOGOUT_INITIATOR_KEY, "true");
    }
    getChannel().postMessage({ type: "logout" });
  } catch {}
}

export function broadcastSessionExpired() {
  try {
    getChannel().postMessage({ type: "session-expired" });
  } catch {}
}

// AuthExpiredModal
function AuthExpiredModal({
  message,
  onConfirm,
}: {
  message: string;
  onConfirm: () => void;
}) {
  return (
    <div
      className="fixed inset-0 flex items-center justify-center bg-black/40 backdrop-blur-sm"
      style={{ zIndex: 9999 }}
    >
      <div
        className="bg-white border-2 border-fg p-6 w-80 shadow-lg"
        style={{ borderRadius: "120px 8px 90px 8px / 8px 90px 8px 120px" }}
      >
        <h3 className="font-heading text-xl text-fg mb-4">Phiên đăng nhập kết thúc</h3>
        <p className="font-body text-fg/70 mb-4">{message}</p>
        <button
          onClick={onConfirm}
          className="w-full py-2 px-4 bg-fg text-white font-body text-lg hover:bg-accent transition-colors"
          style={{ borderRadius: "255px 15px 225px 15px / 15px 225px 15px 255px" }}
        >
          Đăng nhập lại
        </button>
      </div>
    </div>
  );
}

interface AuthSyncProviderProps {
  children: ReactNode;
}

export function AuthSyncProvider({ children }: AuthSyncProviderProps) {
  const router = useRouter();
  const pathname = usePathname();
  const [showModal, setShowModal] = useState(false);
  const [modalMessage, setModalMessage] = useState("");

  const handleEvent = useCallback(
    async (type: AuthEventType) => {
      switch (type) {
        case "login": {
          // Refresh session without page reload
          try {
            await fetch("/api/auth/session", { cache: "no-store" });
            router.refresh();
          } catch {}
          break;
        }
        case "logout": {
          // Don't show modal if this tab initiated the logout
          if (typeof window !== "undefined" && sessionStorage.getItem(LOGOUT_INITIATOR_KEY)) {
            sessionStorage.removeItem(LOGOUT_INITIATOR_KEY);
            return;
          }
          setModalMessage("Bạn đã đăng xuất ở tab khác.");
          setShowModal(true);
          break;
        }
        case "session-expired": {
          setModalMessage("Phiên đăng nhập đã hết hạn.");
          setShowModal(true);
          break;
        }
      }
    },
    [router]
  );

  useEffect(() => {
    if (typeof window === "undefined") return;

    const ch = new BroadcastChannel(CHANNEL_NAME);

    ch.onmessage = (event: MessageEvent) => {
      const { type } = event.data;
      if (type === "login" || type === "logout" || type === "session-expired") {
        handleEvent(type);
      }
    };

    return () => {
      ch.close();
    };
  }, [handleEvent]);

  // Periodic session check — only on protected pages
  useEffect(() => {
    const publicPaths = ["/", "/login", "/register", "/forgot-password",
      "/verify-email", "/verify-otp", "/verify-request", "/auth-error", "/reset-password"];

    const interval = setInterval(async () => {
      // Skip check on public pages (user is not expected to be logged in)
      if (publicPaths.some((p) => pathname === p || pathname.startsWith(p + "/"))) return;

      try {
        const res = await fetch("/api/auth/session", { cache: "no-store" });
        if (res.ok) {
          const session = await res.json();
          if (!session?.user) {
            broadcastSessionExpired();
          }
        }
      } catch {
        // Network error, ignore
      }
    }, SESSION_CHECK_INTERVAL);

    return () => clearInterval(interval);
  }, [pathname]);

  // Check session on mount: if logged in and on public page, redirect to dashboard
  useEffect(() => {
    const publicPaths = ["/", "/login", "/register", "/forgot-password"];
    if (!publicPaths.includes(pathname)) return;

    const checkAndRedirect = async () => {
      try {
        const res = await fetch("/api/auth/session", { cache: "no-store" });
        if (res.ok) {
          const session = await res.json();
          if (session?.user) {
            router.push("/dashboard");
          }
        }
      } catch {
        // Ignore
      }
    };

    checkAndRedirect();
  }, [pathname, router]);

  const handleModalConfirm = () => {
    setShowModal(false);
    router.push("/login");
  };

  return (
    <AuthSyncContext.Provider
      value={{ broadcastLogin, broadcastLogout, broadcastSessionExpired }}
    >
      {children}
      {showModal && (
        <AuthExpiredModal message={modalMessage} onConfirm={handleModalConfirm} />
      )}
    </AuthSyncContext.Provider>
  );
}
