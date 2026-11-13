import type { Conversation, Message, TtlSeconds, User } from "./types";
const base = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");
export const AUTH_EXPIRED_EVENT = "whisper:auth-expired";
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
async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body) headers.set("Content-Type", "application/json");
  let response: Response;
  try {
    response = await fetch(`${base}/api${path}`, {
      ...options,
      credentials: "include",
      headers,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError")
      throw error;
    throw new ApiError("暂时无法连接服务，请稍后重试", 0);
  }
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    if (
      response.status === 401 &&
      !path.startsWith("/auth/") &&
      typeof window !== "undefined"
    )
      window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT));
    throw new ApiError(
      data?.error?.message || `请求失败（${response.status}）`,
      response.status,
      data?.error?.code,
    );
  }
  return data as T;
}
export const getMe = (_userId?: number) => request<User>("/me");
export const searchUsers = (
  _userId: number,
  query: string,
  signal?: AbortSignal,
) =>
  request<User[]>(`/users/search?q=${encodeURIComponent(query)}`, { signal });
export const listConversations = (_userId: number) =>
  request<Conversation[]>("/conversations");
export const createConversation = (_userId: number, otherUserId: number) =>
  request<Conversation>("/conversations", {
    method: "POST",
    body: JSON.stringify({ user_id: otherUserId }),
  });
export const listMessages = (
  _userId: number,
  conversationId: number,
  before?: number,
) =>
  request<Message[]>(
    `/conversations/${conversationId}/messages?limit=50${before ? `&before=${before}` : ""}`,
  );
export const updateConversationTtl = (
  _userId: number,
  conversationId: number,
  ttl: TtlSeconds,
) =>
  request<Conversation>(`/conversations/${conversationId}/ttl`, {
    method: "PATCH",
    body: JSON.stringify({ ttl_seconds: ttl }),
  });
export const markConversationRead = (
  _userId: number,
  conversationId: number,
  lastMessageId: number,
) => request<Conversation>(`/conversations/${conversationId}/read`, {
  method: "POST",
  body: JSON.stringify({ last_message_id: lastMessageId }),
});
function websocketBase(): string {
  const origin =
    import.meta.env.VITE_WS_BASE_URL ||
    `${location.protocol === "https:" ? "wss:" : "ws:"}//${location.host}`;
  return origin.replace(/\/$/, "");
}
export const socketUrl = (_userId: number, conversationId: number) =>
  `${websocketBase()}/ws/conversations/${conversationId}`;
export const eventsSocketUrl = () => `${websocketBase()}/ws/events`;
export const sendEmailCode = (email: string, purpose: "register" | "login") =>
  request<{ message: string; retry_after: number }>("/auth/email-code", {
    method: "POST",
    body: JSON.stringify({ email, purpose }),
  });
export const loginWithPassword = (username: string, password: string) =>
  request<{ user: User }>("/auth/login/password", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
export const loginWithEmail = (email: string, code: string) =>
  request<{ user: User }>("/auth/login/email", {
    method: "POST",
    body: JSON.stringify({ email, code }),
  });
export const register = (fields: {
  username: string;
  display_name: string;
  password: string;
  email: string;
  code: string;
}) =>
  request<{ user: User }>("/auth/register", {
    method: "POST",
    body: JSON.stringify(fields),
  });
export const logout = () =>
  request<Record<string, never>>("/auth/logout", { method: "POST" });
