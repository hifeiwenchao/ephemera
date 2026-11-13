export type TtlSeconds = null | 3600 | 86400 | 604800 | 2592000;
export interface User {
  id: number;
  username: string;
  display_name: string;
  avatar_url: string | null;
  email?: string | null;
}
export interface Message {
  id: number;
  conversation_id: number;
  sender_id: number;
  body: string;
  created_at: string;
  expires_at: string | null;
}
export interface Conversation {
  id: number;
  other_user: User;
  ttl_seconds: TtlSeconds;
  updated_at: string;
  created_at: string;
  last_message: Message | null;
  unread_count: number;
  other_last_read_message_id: number | null;
}
export interface SocketEvent {
  type: string;
  data?: unknown;
  code?: string;
  message?: string;
}
