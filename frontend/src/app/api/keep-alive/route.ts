import { NextResponse } from "next/server";

const BACKEND_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

// This route is called periodically by a Vercel Cron Job to keep
// the HuggingFace Space awake (free tier sleeps after ~48h inactivity).
export async function GET() {
  try {
    const res = await fetch(`${BACKEND_URL}/health`, {
      method: "GET",
      signal: AbortSignal.timeout(10000),
    });

    return NextResponse.json({
      ok: res.ok,
      status: res.status,
      timestamp: new Date().toISOString(),
    });
  } catch (err: any) {
    return NextResponse.json(
      { ok: false, error: err?.message || "Failed to reach backend", timestamp: new Date().toISOString() },
      { status: 503 }
    );
  }
}
