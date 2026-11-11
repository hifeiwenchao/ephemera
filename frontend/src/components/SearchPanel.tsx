import {
  ArrowUpRight,
  LoaderCircle,
  Search,
  UserRoundSearch,
} from "lucide-react";
import type { User } from "../types";
import Avatar from "./Avatar";
export default function SearchPanel({
  query,
  users,
  loading,
  creating,
  onSelect,
}: {
  query: string;
  users: User[];
  loading: boolean;
  creating: number | null;
  onSelect: (user: User) => void;
}) {
  if (query.trim().length < 2)
    return (
      <div className="sidebar-empty">
        <UserRoundSearch size={30} strokeWidth={1.25} />
        <strong>认识一位新朋友</strong>输入至少 2 个字符
        <br />
        按用户名搜索，开启一段对话
      </div>
    );
  if (loading)
    return (
      <div className="sidebar-empty">
        <LoaderCircle size={23} className="spin" />
        正在寻找…
      </div>
    );
  if (!users.length)
    return (
      <div className="sidebar-empty">
        <Search size={29} strokeWidth={1.25} />
        <strong>还没有找到「{query}」</strong>试试其他用户名，如 alice 或 bob
      </div>
    );
  return (
    <>
      {users.map((user) => (
        <button
          className="search-result"
          key={user.id}
          disabled={creating !== null}
          onClick={() => onSelect(user)}
          aria-label={`与${user.display_name}开始聊天`}
        >
          <Avatar user={user} />
          <div className="conversation-details">
            <div className="conversation-name">{user.display_name}</div>
            <div className="conversation-preview">@{user.username}</div>
          </div>
          {creating === user.id ? (
            <LoaderCircle size={16} className="spin" />
          ) : (
            <ArrowUpRight size={17} className="start-chat" />
          )}
        </button>
      ))}
    </>
  );
}
