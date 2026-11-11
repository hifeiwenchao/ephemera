import type { User } from "../types";
const palettes = [
  { background: "#e8d9c9", color: "#806a54" },
  { background: "#dce6ce", color: "#71874e" },
  { background: "#e7dee9", color: "#8f739a" },
  { background: "#d7e3e7", color: "#688591" },
  { background: "#e9dfcf", color: "#9f845d" },
];
export default function Avatar({
  user,
  size = "",
  online = false,
}: {
  user?: User | null;
  size?: string;
  online?: boolean;
}) {
  const name = user?.display_name || user?.username || "轻";
  return (
    <div
      className={`avatar ${size}`}
      style={palettes[((user?.id || 1) - 1) % palettes.length]}
      aria-hidden="true"
    >
      {user?.avatar_url ? (
        <img src={user.avatar_url} alt="" />
      ) : name.match(/[\u4e00-\u9fff]/) ? (
        name.slice(-1)
      ) : (
        name.slice(0, 1).toUpperCase()
      )}
      {online && <span className="online-dot" />}
    </div>
  );
}
