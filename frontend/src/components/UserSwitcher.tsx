import { useEffect, useRef, useState } from "react";
import { Check } from "lucide-react";
import type { User } from "../types";
import Avatar from "./Avatar";
export default function UserSwitcher({
  users,
  currentUser,
  onChange,
}: {
  users: User[];
  currentUser: User | null;
  onChange: (id: number) => void;
}) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const close = (event: MouseEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", escape);
    };
  }, []);
  return (
    <div className="rail-bottom" ref={root}>
      <button
        className="identity-trigger"
        aria-label="切换演示用户"
        title="切换演示用户"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        <Avatar user={currentUser} size="small" />
      </button>
      {open && (
        <div className="popover user-popover">
          <div className="popover-title">切换演示身份</div>
          <div className="popover-description">以不同身份体验实时对话</div>
          {users.map((user) => (
            <button
              key={user.id}
              className={`user-option ${user.id === currentUser?.id ? "current" : ""}`}
              onClick={() => {
                onChange(user.id);
                setOpen(false);
              }}
            >
              <Avatar user={user} size="small" />
              <div>
                <div className="user-option-name">{user.display_name}</div>
                <div className="user-option-handle">@{user.username}</div>
              </div>
              {user.id === currentUser?.id && (
                <Check size={14} className="option-check" />
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
