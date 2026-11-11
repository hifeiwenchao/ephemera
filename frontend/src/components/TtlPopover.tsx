import { useEffect, useRef, useState } from "react";
import {
  Check,
  ChevronDown,
  Clock3,
  LoaderCircle,
  TimerOff,
} from "lucide-react";
import { ttlLabel, ttlOptions } from "../display";
import type { TtlSeconds } from "../types";
export default function TtlPopover({
  value,
  onChange,
}: {
  value: TtlSeconds;
  onChange: (ttl: TtlSeconds) => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
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
  async function select(ttl: TtlSeconds) {
    setSaving(true);
    try {
      await onChange(ttl);
      setOpen(false);
    } catch {
      /* App surfaces server errors. */
    } finally {
      setSaving(false);
    }
  }
  return (
    <div className="ttl-wrap" ref={root}>
      <button
        className={`ttl-trigger ${value ? "active" : ""}`}
        onClick={() => setOpen(!open)}
        aria-label={`自动删除：${ttlLabel(value)}`}
        aria-expanded={open}
        title="设置消息自动删除"
      >
        <Clock3 size={14} />
        {value ? `${ttlLabel(value)}后删除` : "自动删除已关闭"}
        <ChevronDown size={12} />
      </button>
      {open && (
        <div className="popover ttl-popover">
          <div className="popover-title">让消息，适时说再见</div>
          <div className="popover-description">
            仅影响设置后发送的新消息。
            <br />
            到期后，将从双方的会话中删除。
          </div>
          {ttlOptions.map((option) => (
            <button
              className={`ttl-option ${value === option.value ? "current" : ""}`}
              key={option.label}
              disabled={saving}
              onClick={() => void select(option.value)}
            >
              {option.value ? <Clock3 size={14} /> : <TimerOff size={14} />}
              {option.label}
              {value === option.value &&
                (saving ? (
                  <LoaderCircle size={14} className="option-check spin" />
                ) : (
                  <Check size={14} className="option-check" />
                ))}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
