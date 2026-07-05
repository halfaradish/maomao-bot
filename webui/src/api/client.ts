import { useAuthStore } from "@/store/authStore";
import toast from "react-hot-toast";

const API_BASE = "/api/v1";

interface ApiResponse<T = unknown> {
  status: "success" | "error";
  message?: string;
  data?: T;
}

interface PaginatedData<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

async function request<T = unknown>(
  method: string,
  path: string,
  body?: unknown
): Promise<ApiResponse<T>> {
  const { token, setToken } = useAuthStore.getState();

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  let res: Response;
  try {
    res = await fetch(API_BASE + path, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch (err) {
    toast.error("网络错误，请检查连接");
    throw err;
  }

  if (res.status === 401) {
    setToken(null);
    toast.error("登录已过期，请重新登录");
    window.location.href = "/login";
    throw new Error("登录已过期");
  }

  let json: ApiResponse<T>;
  try {
    json = await res.json();
  } catch {
    throw new Error(`Invalid response (${res.status})`);
  }

  if (json.status === "error") {
    throw new Error(json.message || "请求失败");
  }

  return json;
}

export function apiGet<T = unknown>(path: string) {
  return request<T>("GET", path);
}

export function apiPost<T = unknown>(path: string, body?: unknown) {
  return request<T>("POST", path, body);
}

export function apiDelete<T = unknown>(path: string) {
  return request<T>("DELETE", path);
}

export type { ApiResponse, PaginatedData };
