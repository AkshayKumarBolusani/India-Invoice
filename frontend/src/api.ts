import type { CompareResult, ProcessResult } from "./types";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Request failed with ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export function health() {
  return request<{ status: string; llm_configured: boolean; llm_model?: string; max_upload_bytes: number }>("/api/health");
}

export function processInvoice(file: File, engine = "rules-based") {
  const body = new FormData();
  body.append("file", file);
  return request<ProcessResult>(`/api/process?engine=${engine}`, { method: "POST", body });
}

export function processBatch(files: File[], engine = "rules-based") {
  const body = new FormData();
  files.forEach((file) => body.append("files", file));
  return request<{ results: ProcessResult[]; total: number; completed: number; failed: number }>(`/api/batch?engine=${engine}`, { method: "POST", body });
}

export function compareInvoice(file: File) {
  const body = new FormData();
  body.append("file", file);
  return request<CompareResult>("/api/compare", { method: "POST", body });
}

export function evaluation() {
  return request<{ available: boolean; reports: Record<string, any>; note: string }>("/api/evaluation");
}

export { API_BASE };
