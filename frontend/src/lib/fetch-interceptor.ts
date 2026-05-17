import { broadcastSessionExpired } from "./auth-sync";

if (typeof window !== "undefined") {
  const originalFetch = window.fetch;

  window.fetch = async function (...args) {
    const response = await originalFetch.apply(this, args);

    if (response.status === 401) {
      // Only broadcast session-expired if there is truly no active user session.
      // NOTE: NextAuth always returns HTTP 200 for /api/auth/session (even when
      // unauthenticated – it just returns {}), so we must inspect the body.
      try {
        const sessionRes = await originalFetch("/api/auth/session", { cache: "no-store" });
        if (sessionRes.ok) {
          const session = await sessionRes.json();
          if (!session?.user) {
            broadcastSessionExpired();
          }
        }
      } catch {
        // Ignore network errors
      }
    }

    return response;
  };
}
