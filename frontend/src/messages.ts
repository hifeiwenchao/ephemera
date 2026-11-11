import type { Message, SocketEvent } from "./types";
export function mergeMessages(
  existing: Message[],
  incoming: Message[],
  now = Date.now(),
): Message[] {
  const unique = new Map(
    [...existing, ...incoming].map((message) => [message.id, message]),
  );
  return [...unique.values()]
    .filter(
      (message) => !message.expires_at || Date.parse(message.expires_at) > now,
    )
    .sort(
      (a, b) =>
        Date.parse(a.created_at) - Date.parse(b.created_at) || a.id - b.id,
    );
}
export function applyMessageEvent(
  existing: Message[],
  event: SocketEvent,
  now = Date.now(),
): Message[] {
  if (event.type === "message.created")
    return mergeMessages(existing, [event.data as Message], now);
  if (event.type === "message.deleted") {
    const ids = new Set((event.data as { ids: number[] }).ids);
    return existing.filter((message) => !ids.has(message.id));
  }
  return existing;
}
