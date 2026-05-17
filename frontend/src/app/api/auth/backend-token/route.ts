import { NextResponse } from "next/server";
import { SignJWT } from "jose";
import { auth } from "@/auth";

async function createBackendAccessToken(userId: string, email: string, role: string): Promise<string> {
  const secret = new TextEncoder().encode(
    process.env.BACKEND_AUTH_SECRET || 
    process.env.AUTH_SECRET || 
    "default-secret-change-in-production"
  );
  return new SignJWT({ email, role })
    .setProtectedHeader({ alg: "HS256" })
    .setSubject(userId)
    .setIssuedAt()
    .setExpirationTime("15m")
    .sign(secret);
}

export async function GET() {
  const session = await auth();

  if (!session?.user?.id) {
    return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
  }

  const token = await createBackendAccessToken(
    session.user.id,
    session.user.email || "",
    session.user.role || "free"
  );

  return NextResponse.json({ accessToken: token });
}
