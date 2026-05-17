import NextAuth, { type DefaultSession, type NextAuthConfig } from "next-auth";
import Google from "next-auth/providers/google";
import GitHub from "next-auth/providers/github";
import Credentials from "next-auth/providers/credentials";
import { compare } from "bcryptjs";
import { createClient } from "@supabase/supabase-js";
import crypto from "crypto";

declare module "next-auth" {
  interface Session {
    user: {
      id: string;
      role: "free" | "premium" | "admin";
    } & DefaultSession["user"];
  }

  interface User {
    role?: "free" | "premium" | "admin";
  }
}

declare module "@auth/core/jwt" {
  interface JWT {
    id?: string;
    role?: "free" | "premium" | "admin";
  }
}

function getSupabase() {
  return createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY!
  );
}

async function findUserByEmail(email: string) {
  const { data: users } = await getSupabase()
    .from("users")
    .select("*")
    .eq("email", email)
    .limit(1);
  return users?.[0] || null;
}

async function updateLinkedProviders(userId: string, provider: string) {
  const { data: user } = await getSupabase()
    .from("users")
    .select("linked_providers")
    .eq("id", userId)
    .single();

  const providers: string[] = user?.linked_providers || [];

  if (!providers.includes(provider)) {
    providers.push(provider);
    await getSupabase()
      .from("users")
      .update({ linked_providers: providers })
      .eq("id", userId);
  }
}

async function createOAuthUser(email: string, name: string, image: string, provider: string) {
  const id = crypto.randomUUID();
  const { data, error } = await getSupabase()
    .from("users")
    .insert({
      id,
      email,
      name,
      image,
      email_verified: new Date().toISOString(),
      linked_providers: [provider],
    })
    .select()
    .single();

  if (error) throw error;

  // Create role
  await getSupabase()
    .from("user_roles")
    .insert({ user_id: id, role: "free" });

  return data;
}

async function getUserRole(userId: string): Promise<"free" | "premium" | "admin"> {
  const { data } = await getSupabase()
    .from("user_roles")
    .select("role")
    .eq("user_id", userId)
    .single();
  return (data?.role as "free" | "premium" | "admin") || "free";
}

const config: NextAuthConfig = {
  logger: {
    error(error) {
      if (error.name === "CredentialsSignin") return;
      console.error(`[auth][error]`, error);
    },
  },

  providers: [
    Google({
      clientId: process.env.AUTH_GOOGLE_ID,
      clientSecret: process.env.AUTH_GOOGLE_SECRET,
    }),
    GitHub({
      clientId: process.env.AUTH_GITHUB_ID,
      clientSecret: process.env.AUTH_GITHUB_SECRET,
    }),
    Credentials({
      name: "credentials",
      credentials: {
        email: { label: "Email", type: "email" },
        password: { label: "Password", type: "password" },
      },
      async authorize(credentials) {
        if (!credentials?.email || !credentials?.password) {
          return null;
        }

        const user = await findUserByEmail(credentials.email as string);
        if (!user || !user.password_hash) {
          return null;
        }

        // Allow OTP auto-login with special password
        const isOtpLogin = credentials.password === "__otp_verified__";

        if (!isOtpLogin) {
          const isValid = await compare(credentials.password as string, user.password_hash);
          if (!isValid) {
            return null;
          }
        }

        if (!user.email_verified) {
          throw new Error("EMAIL_NOT_VERIFIED");
        }

        return {
          id: user.id,
          email: user.email,
          name: user.name,
          image: user.image,
          emailVerified: user.email_verified,
        };
      },
    }),
  ],

  pages: {
    signIn: "/login",
    verifyRequest: "/verify-request",
    error: "/auth-error",
  },

  session: {
    strategy: "jwt",
    maxAge: 7 * 24 * 60 * 60, // 7 days
  },

  callbacks: {
    async signIn({ user, account }) {
      if (account?.provider === "google" || account?.provider === "github") {
        const existing = await findUserByEmail(user.email!);
        if (!existing) {
          // Create new user with provider tracking
          const newUser = await createOAuthUser(
            user.email!,
            user.name || user.email!.split("@")[0],
            user.image || "",
            account.provider
          );
          user.id = newUser.id;
        } else {
          // Existing user: add provider to linked_providers
          user.id = existing.id;
          // Keep original name/image from DB, do NOT override from new provider
          user.name = existing.name;
          user.image = existing.image;
          await updateLinkedProviders(existing.id, account.provider);
        }
      }
      return true;
    },

    async jwt({ token, user, trigger, session }) {
      if (user) {
        token.id = user.id;
        if (user.id) {
          token.role = user.role || await getUserRole(user.id);
        }
      }

      if (trigger === "signUp" && token.id) {
        token.role = "free";
      }

      if (trigger === "update" && session) {
        token.name = session.name;
        token.email = session.email;
      }

      return token;
    },

    async session({ session, token }) {
      if (token.id && session.user) {
        session.user.id = token.id as string;
        session.user.role = token.role || "free";
      }
      return session;
    },
  },
};

export const { handlers, signIn, signOut, auth } = NextAuth(config);
