import { useCallback, useEffect, useRef, useState } from "react";
import {
  ArrowUpRight,
  Check,
  Feather,
  Leaf,
  LogOut,
  LoaderCircle,
  MessageCircle,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  X,
} from "lucide-react";
import {
  AUTH_EXPIRED_EVENT,
  createConversation,
  getMe,
  listConversations,
  logout,
  searchUsers,
  updateConversationTtl,
} from "./api";
import type { Conversation, TtlSeconds, User } from "./types";
import { ttlLabel } from "./display";
import { ConversationActivityGuard } from "./conversationState";
import { useConversation } from "./hooks/useConversation";
import Avatar from "./components/Avatar";
import ChatHeader from "./components/ChatHeader";
import ConversationList from "./components/ConversationList";
import MessageComposer from "./components/MessageComposer";
import MessageList from "./components/MessageList";
import SearchPanel from "./components/SearchPanel";
import AuthScreen from "./components/AuthScreen";
const sortConversations = (conversations: Conversation[]) =>
  [...conversations].sort(
    (a, b) => Date.parse(b.updated_at) - Date.parse(a.updated_at),
  );
export default function App() {
  const [currentUserId, setCurrentUserId] = useState<number | null>(null);
  const [currentUser, setCurrentUser] = useState<User | null>(null);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<User[]>([]);
  const [searching, setSearching] = useState(false);
  const [loading, setLoading] = useState(true);
  const [authChecked, setAuthChecked] = useState(false);
  const [creating, setCreating] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [showInfo, setShowInfo] = useState(false);
  const searchInput = useRef<HTMLInputElement>(null);
  const identity = useRef(currentUserId);
  const activityGuard = useRef(new ConversationActivityGuard());
  identity.current = currentUserId;
  useEffect(() => {
    let cancelled = false;
    const expired = () => {
      if (!cancelled) {
        setCurrentUser(null);
        setCurrentUserId(null);
        setConversations([]);
        setSelectedId(null);
      }
    };
    window.addEventListener(AUTH_EXPIRED_EVENT, expired);
    getMe()
      .then((user) => {
        if (!cancelled) {
          setCurrentUser(user);
          setCurrentUserId(user.id);
        }
      })
      .catch((cause) => {
        if (!cancelled && cause?.status !== 401)
          setError(cause instanceof Error ? cause.message : "暂时无法连接服务");
      })
      .finally(() => {
        if (!cancelled) {
          setAuthChecked(true);
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
      window.removeEventListener(AUTH_EXPIRED_EVENT, expired);
    };
  }, []);
  useEffect(() => {
    if (!currentUserId) return;
    let cancelled = false;
    const userId = currentUserId;
    setLoading(true);
    setError("");
    setConversations([]);
    setSelectedId(null);
    setQuery("");
    setResults([]);
    setCreating(null);
    setShowInfo(false);
    const initialRevision = activityGuard.current.beginRequest();
    Promise.all([getMe(userId), listConversations(userId)])
      .then(([me, items]) => {
        if (cancelled) return;
        setCurrentUser(me);
        setConversations((previous) =>
          activityGuard.current.applySnapshot(
            previous,
            sortConversations(items),
            initialRevision,
          ),
        );
        if (window.matchMedia("(min-width: 761px)").matches)
          setSelectedId(items[0]?.id || null);
      })
      .catch((cause) => {
        if (!cancelled) setError(cause.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    const refresh = () => {
      const requestRevision = activityGuard.current.beginRequest();
      return listConversations(userId)
        .then((items) => {
          if (!cancelled)
            setConversations((previous) =>
              activityGuard.current.applySnapshot(
                previous,
                sortConversations(items),
                requestRevision,
              ),
            );
        })
        .catch(() => {
          /* The conversation and connection states preserve current content during background failures. */
        });
    };
    const timer = setInterval(refresh, 15000);
    window.addEventListener("focus", refresh);
    return () => {
      cancelled = true;
      clearInterval(timer);
      window.removeEventListener("focus", refresh);
    };
  }, [currentUserId]);
  useEffect(() => {
    if (!currentUserId || query.trim().length < 2) {
      setResults([]);
      setSearching(false);
      return;
    }
    const controller = new AbortController();
    setSearching(true);
    const timeout = setTimeout(() => {
      searchUsers(currentUserId, query.trim(), controller.signal)
        .then((data) => {
          if (!controller.signal.aborted) setResults(data);
        })
        .catch((cause) => {
          if (!controller.signal.aborted) {
            setError(cause.message);
            setResults([]);
          }
        })
        .finally(() => {
          if (!controller.signal.aborted) setSearching(false);
        });
    }, 250);
    return () => {
      clearTimeout(timeout);
      controller.abort();
    };
  }, [query, currentUserId]);
  useEffect(() => {
    const timer = setInterval(
      () =>
        setConversations((previous) =>
          previous.some(
            (item) =>
              item.last_message?.expires_at &&
              Date.parse(item.last_message.expires_at) <= Date.now(),
          )
            ? previous.map((item) =>
                item.last_message?.expires_at &&
                Date.parse(item.last_message.expires_at) <= Date.now()
                  ? { ...item, last_message: null }
                  : item,
              )
            : previous,
        ),
      1000,
    );
    return () => clearInterval(timer);
  }, []);
  const onActivity = useCallback(
    (update: Partial<Conversation> & { id: number }) => {
      activityGuard.current.recordActivity();
      setConversations((previous) =>
        sortConversations(
          previous.map((item) =>
            item.id === update.id ? { ...item, ...update } : item,
          ),
        ),
      );
    },
    [],
  );
  const live = useConversation(currentUserId, selectedId, onActivity);
  const selected =
    conversations.find((conversation) => conversation.id === selectedId) ||
    null;
  async function startConversation(user: User) {
    if (!currentUserId) return;
    const userId = currentUserId;
    setCreating(user.id);
    setError("");
    try {
      const requestRevision = activityGuard.current.beginRequest();
      const conversation = await createConversation(userId, user.id);
      if (identity.current !== userId) return;
      setConversations((previous) =>
        sortConversations(
          activityGuard.current.applyConversationResponse(
            previous,
            conversation,
            requestRevision,
          ),
        ),
      );
      setSelectedId(conversation.id);
      setQuery("");
      const refreshRevision = activityGuard.current.beginRequest();
      const items = await listConversations(userId);
      if (identity.current === userId)
        setConversations((previous) =>
          activityGuard.current.applySnapshot(
            previous,
            sortConversations(items),
            refreshRevision,
          ),
        );
    } catch (cause) {
      if (identity.current === userId)
        setError(cause instanceof Error ? cause.message : "无法创建会话");
    } finally {
      if (identity.current === userId) setCreating(null);
    }
  }
  async function changeTtl(ttl: TtlSeconds) {
    if (!currentUserId || !selected) return;
    const userId = currentUserId;
    try {
      const requestRevision = activityGuard.current.beginRequest();
      const updated = await updateConversationTtl(userId, selected.id, ttl);
      if (
        identity.current === userId &&
        activityGuard.current.beginRequest() === requestRevision
      )
        onActivity(updated);
    } catch (cause) {
      if (identity.current === userId)
        setError(cause instanceof Error ? cause.message : "设置失败");
      throw cause;
    }
  }
  function beginSearch() {
    searchInput.current?.focus();
  }
  const visibleError = error || live.error;
  if (!authChecked)
    return (
      <div className="auth-loading">
        <LoaderCircle size={22} className="spin" />
      </div>
    );
  if (!currentUser)
    return (
      <AuthScreen
        onAuthenticated={(user) => {
          setCurrentUser(user);
          setCurrentUserId(user.id);
          setError("");
        }}
      />
    );
  return (
    <div className={`app-shell ${selected ? "conversation-open" : ""}`}>
      <aside className="brand-rail" aria-label="Ephemera">
        <div className="brand-mark" title="Ephemera">
          <Feather size={25} strokeWidth={1.7} />
        </div>
        <div className="rail-divider" />
        <button
          className="rail-active"
          aria-label="消息列表"
          title="消息列表"
          onClick={() => {
            setQuery("");
            if (window.matchMedia("(max-width: 760px)").matches)
              setSelectedId(null);
          }}
        >
          <MessageCircle size={22} strokeWidth={1.6} />
        </button>
        <div className="rail-caption">LESS NOISE. MORE CONNECTION.</div>
        <div className="profile-rail">
          <button
            className="identity-trigger"
            aria-label="账户设置"
            title="账户设置"
          >
            <Avatar user={currentUser} size="small" />
          </button>
          <button
            className="logout-rail"
            aria-label="退出登录"
            title="退出登录"
            onClick={() =>
              void logout().finally(() => {
                setCurrentUser(null);
                setCurrentUserId(null);
              })
            }
          >
            <LogOut size={14} />
          </button>
        </div>
      </aside>
      <aside className="sidebar" aria-label="会话列表">
        <div className="sidebar-header">
          <div>
            <h1>
              Ephemera
              <span style={{ color: "#75a16c", fontSize: 19, marginLeft: 3 }}>
                .
              </span>
            </h1>
            <div className="brand-subtitle">EPHEMERA / 私密消息</div>
          </div>
          <button
            className="icon-button"
            aria-label="发起新对话"
            title="发起新对话"
            onClick={beginSearch}
          >
            <Plus size={23} strokeWidth={1.5} />
          </button>
        </div>
        <label className="sidebar-search">
          <Search size={16} strokeWidth={1.5} />
          <input
            ref={searchInput}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="搜索用户名，开启新的对话"
            aria-label="搜索用户名"
          />
          {query ? (
            <button
              className="icon-button"
              style={{ width: 18, height: 22 }}
              aria-label="清除搜索"
              onClick={() => setQuery("")}
            >
              <X size={13} />
            </button>
          ) : (
            <span className="search-shortcut">⌕</span>
          )}
        </label>
        <div className="list-heading">
          {query.trim() ? "搜索用户" : "全部消息"}
          <span className="count">
            {query.trim() ? results.length : conversations.length}
          </span>
          <SlidersHorizontal size={13} strokeWidth={1.3} aria-hidden="true" />
        </div>
        <div className="conversation-list">
          {query.trim() ? (
            <SearchPanel
              query={query}
              users={results}
              loading={searching}
              creating={creating}
              onSelect={(user) => void startConversation(user)}
            />
          ) : (
            <ConversationList
              conversations={conversations}
              selectedId={selectedId}
              userId={currentUserId}
              loading={loading}
              onSelect={(id) => {
                setSelectedId(id);
                setShowInfo(false);
              }}
            />
          )}
        </div>
        {error && !selected && (
          <div className="error-inline" role="alert">
            <span>{error}</span>
            <button
              className="retry-button"
              onClick={() => {
                setError("");
                setLoading(true);
                getMe()
                  .then((user) => {
                    setCurrentUser(user);
                    setCurrentUserId(user.id);
                  })
                  .catch((cause) =>
                    setError(
                      cause instanceof Error
                        ? cause.message
                        : "暂时无法连接服务",
                    ),
                  );
              }}
            >
              <RefreshCw size={12} />
              重新连接服务
            </button>
          </div>
        )}
        <div className="sidebar-footer">
          <Leaf size={17} strokeWidth={1.3} />
          <div>
            留一点空间，给真实的连接
            <span>
              {currentUser
                ? `当前账户：${currentUser.display_name} · @${currentUser.username}`
                : "一个轻盈、自在的聊天空间"}
            </span>
          </div>
        </div>
      </aside>
      <main className="chat-panel chat-pattern">
        {selected && currentUser ? (
          <>
            <ChatHeader
              conversation={selected}
              connection={live.connection}
              onBack={() => setSelectedId(null)}
              onTtlChange={changeTtl}
              onInfo={() => setShowInfo(true)}
            />
            {(live.connection === "reconnecting" ||
              live.connection === "disconnected") && (
              <div className="connection-banner">
                <RefreshCw
                  size={12}
                  className={live.connection === "reconnecting" ? "spin" : ""}
                />
                {live.connection === "reconnecting"
                  ? "连接暂时中断，正在重新连接。草稿已保留。"
                  : "实时连接已断开，草稿已保留。"}
                {live.connection === "disconnected" && (
                  <button onClick={live.reconnect}>重新连接</button>
                )}
              </div>
            )}
            <MessageList
              key={`${currentUserId}:${selectedId}`}
              messages={live.messages}
              currentUser={currentUser}
              otherUser={selected.other_user}
              loading={live.loading}
              hasMore={live.hasMore}
              loadingOlder={live.loadingOlder}
              onLoadOlder={live.loadOlder}
            />
            <MessageComposer
              key={`${currentUserId}:${selectedId}:composer`}
              draftKey={`whisper-draft:${currentUserId}:${selectedId}`}
              connected={live.connection === "connected"}
              ttl={selected.ttl_seconds}
              onSend={live.send}
            />
          </>
        ) : (
          <div className="empty-chat">
            <div className="welcome-pill">
              <Sparkles size={10} /> A LITTLE CLOSER
            </div>
            <div className="empty-art">
              <div className="empty-art-mark">
                <Feather size={43} strokeWidth={1.25} />
              </div>
              <Sparkles className="art-spark" size={24} strokeWidth={1} />
            </div>
            <h2>轻一点，聊得近一点</h2>
            <p>
              从一句「你好」开始。
              <br />
              在这里，把时间留给在意的人。
            </p>
            <button className="primary-button" onClick={beginSearch}>
              开启一段对话
              <ArrowUpRight size={15} />
            </button>
            <div className="empty-feature">
              <ClockIcon />
              消息自动删除
              <span style={{ margin: "0 8px", color: "#c3cbb9" }}>·</span>
              <Feather size={12} />
              轻盈纯粹的交流
            </div>
          </div>
        )}
        {visibleError && selected && (
          <div className="toast-error" role="alert">
            <span>{visibleError}</span>
            {!loading && !currentUserId && (
              <button
                aria-label="重试连接服务"
                onClick={() => {
                  setError("");
                  setLoading(true);
                  getMe()
                    .then((user) => {
                      setCurrentUser(user);
                      setCurrentUserId(user.id);
                    })
                    .catch((cause) =>
                      setError(
                        cause instanceof Error
                          ? cause.message
                          : "暂时无法连接服务",
                      ),
                    );
                }}
              >
                <RefreshCw size={14} />
              </button>
            )}
            <button
              aria-label="关闭错误提示"
              onClick={() => {
                setError("");
                live.clearError();
              }}
            >
              <X size={13} />
            </button>
          </div>
        )}
        {showInfo && selected && (
          <div
            className="info-overlay"
            onClick={(event) => {
              if (event.target === event.currentTarget) setShowInfo(false);
            }}
          >
            <section
              className="info-card"
              role="dialog"
              aria-modal="true"
              aria-label="会话资料"
              onKeyDown={(event) => {
                if (event.key === "Escape") setShowInfo(false);
              }}
            >
              <button
                autoFocus
                className="icon-button"
                aria-label="关闭会话资料"
                onClick={() => setShowInfo(false)}
              >
                <X size={18} />
              </button>
              <Avatar user={selected.other_user} size="jumbo" />
              <h3>{selected.other_user.display_name}</h3>
              <div className="handle">@{selected.other_user.username}</div>
              <div className="info-detail">
                <ClockIcon />
                消息自动删除<strong>{ttlLabel(selected.ttl_seconds)}</strong>
              </div>
              <p>
                这是你们的专属对话空间。
                <br />
                自动删除设置仅影响之后发送的新消息。
              </p>
              <div className="info-detail">
                <ShieldCheck size={15} />
                本地原型 · 演示身份
                <Check size={14} style={{ marginLeft: "auto" }} />
              </div>
            </section>
          </div>
        )}
      </main>
    </div>
  );
}
function ClockIcon() {
  return (
    <svg
      width="12"
      height="12"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="8" />
      <path d="M12 7v5l3 2" />
    </svg>
  );
}
