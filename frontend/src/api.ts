import type { Conversation, Message, TtlSeconds, User } from "./types";
const base = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");
export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public code?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}
async function request<T>(
  path: string,
  userId?: number,
  options: RequestInit = {},
): Promise<T> {
  const headers = new Headers(options.headers);
  if (userId !== undefined) headers.set("X-User-Id", String(userId));
  if (options.body) headers.set("Content-Type", "application/json");
  let response: Response;
  try {
    response = await fetch(`${base}/api${path}`, { ...options, headers });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError")
      throw error;
    throw new ApiError("暂时无法连接服务，请稍后重试", 0);
  }
  const data = await response.json().catch(() => null);
  if (!response.ok)
    throw new ApiError(
      data?.error?.message || `请求失败（${response.status}）`,
      response.status,
      data?.error?.code,
    );
  return data as T;
}
export const getDemoUsers = () => request<User[]>("/demo-users");
export const getMe = (userId: number) => request<User>("/me", userId);
export const searchUsers = (
  userId: number,
  query: string,
  signal?: AbortSignal,
) =>
  request<User[]>(`/users/search?q=${encodeURIComponent(query)}`, userId, {
    signal,
  });
export const listConversations = (userId: number) =>
  request<Conversation[]>("/conversations", userId);
export const createConversation = (userId: number, otherUserId: number) =>
  request<Conversation>("/conversations", userId, {
    method: "POST",
    body: JSON.stringify({ user_id: otherUserId }),
  });
export const listMessages = (
  userId: number,
  conversationId: number,
  before?: number,
) =>
  request<Message[]>(
    `/conversations/${conversationId}/messages?limit=50${before ? `&before=${before}` : ""}`,
    userId,
  );
export const updateConversationTtl = (
  userId: number,
  conversationId: number,
  ttl: TtlSeconds,
) =>
  request<Conversation>(`/conversations/${conversationId}/ttl`, userId, {
    method: "PATCH",
    body: JSON.stringify({ ttl_seconds: ttl }),
  });
export function socketUrl(userId: number, conversationId: number): string {
  const origin =
    import.meta.env.VITE_WS_BASE_URL ||
    `${location.protocol === "https:" ? "wss:" : "ws:"}//${location.host}`;
  return `${origin.replace(/\/$/, "")}/ws/conversations/${conversationId}?user_id=${userId}`;
}
