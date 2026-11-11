import { FormEvent, ReactNode, useEffect, useState } from "react";
import {
  ArrowRight,
  CheckCircle2,
  Feather,
  LoaderCircle,
  Mail,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";
import {
  loginWithEmail,
  loginWithPassword,
  register,
  sendEmailCode,
} from "../api";
import { AuthFields, AuthMode, normalizeEmail, validateAuth } from "../auth";
import type { User } from "../types";
const empty: AuthFields = {
  username: "",
  display_name: "",
  password: "",
  email: "",
  code: "",
};
export default function AuthScreen({
  onAuthenticated,
}: {
  onAuthenticated: (user: User) => void;
}) {
  const [mode, setMode] = useState<AuthMode>("password");
  const [fields, setFields] = useState<AuthFields>(empty);
  const [errors, setErrors] = useState<
    Partial<Record<keyof AuthFields, string>>
  >({});
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [sending, setSending] = useState(false);
  const [retryAfter, setRetryAfter] = useState(0);
  useEffect(() => {
    if (!retryAfter) return;
    const timer = setInterval(
      () => setRetryAfter((value) => Math.max(0, value - 1)),
      1000,
    );
    return () => clearInterval(timer);
  }, [retryAfter]);
  function change(key: keyof AuthFields, value: string) {
    setFields((previous) => ({ ...previous, [key]: value }));
    setErrors((previous) => ({ ...previous, [key]: undefined }));
    setError("");
  }
  function switchMode(next: AuthMode) {
    setMode(next);
    setErrors({});
    setError("");
    if (next === "register")
      setFields((previous) => ({ ...previous, password: "", code: "" }));
  }
  async function sendCode() {
    const email = normalizeEmail(fields.email);
    const emailError = validateAuth(
      mode === "register" ? "register" : "email",
      { ...fields, email },
    ).email;
    if (emailError || sending || retryAfter) {
      setErrors((previous) => ({ ...previous, email: emailError }));
      return;
    }
    setSending(true);
    setError("");
    try {
      const result = await sendEmailCode(
        email,
        mode === "register" ? "register" : "login",
      );
      setRetryAfter(result.retry_after || 60);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "验证码发送失败");
    } finally {
      setSending(false);
    }
  }
  async function submit(event: FormEvent) {
    event.preventDefault();
    const next = { ...fields, email: normalizeEmail(fields.email) };
    const validation = validateAuth(mode, next);
    setFields(next);
    setErrors(validation);
    setError("");
    if (Object.keys(validation).length) return;
    setBusy(true);
    try {
      const result =
        mode === "register"
          ? await register({
              username: next.username.trim(),
              display_name: next.display_name.trim(),
              password: next.password,
              email: next.email,
              code: next.code,
            })
          : mode === "password"
            ? await loginWithPassword(next.username.trim(), next.password)
            : await loginWithEmail(next.email, next.code);
      onAuthenticated(result.user);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "操作失败，请稍后重试");
    } finally {
      setBusy(false);
    }
  }
  const emailMode = mode !== "password";
  const registerMode = mode === "register";
  return (
    <main className="auth-shell">
      <div className="auth-art">
        <div className="auth-orbit auth-orbit-one" />
        <div className="auth-orbit auth-orbit-two" />
        <div className="auth-mark">
          <Feather size={45} strokeWidth={1.35} />
        </div>
        <div className="auth-sprig">✦</div>
      </div>
      <section className="auth-card">
        <div className="auth-brand">
          <div className="brand-mark">
            <Feather size={24} />
          </div>
          <div>
            <h1>
              Ephemera<span>.</span>
            </h1>
            <p>EPHEMERA / 私密消息</p>
          </div>
        </div>
        <div className="auth-copy">
          <h2>{registerMode ? "创建你的 Ephemera" : "欢迎回来"}</h2>
          <p>
            {registerMode
              ? "用邮箱验证，开启一段自在的对话。"
              : "把时间留给在意的人。"}
          </p>
        </div>
        {!registerMode && (
          <div className="auth-tabs">
            <button
              className={mode === "password" ? "active" : ""}
              onClick={() => switchMode("password")}
            >
              用户名密码
            </button>
            <button
              className={mode === "email" ? "active" : ""}
              onClick={() => switchMode("email")}
            >
              邮箱验证码
            </button>
          </div>
        )}
        <form className="auth-form" onSubmit={submit} noValidate>
          {registerMode && (
            <Field
              label="用户名"
              value={fields.username}
              onChange={(value) => change("username", value)}
              error={errors.username}
              placeholder="3–32 位字母、数字或下划线"
              autoComplete="username"
            />
          )}{" "}
          {registerMode && (
            <Field
              label="显示名称（可选）"
              value={fields.display_name}
              onChange={(value) => change("display_name", value)}
              error={errors.display_name}
              placeholder="别人看到的名字"
              autoComplete="name"
            />
          )}
          {(!emailMode || registerMode) && !registerMode && (
            <Field
              label="用户名或邮箱"
              value={fields.username}
              onChange={(value) => change("username", value)}
              error={errors.username}
              placeholder="输入用户名或已绑定邮箱"
              autoComplete="username"
            />
          )}
          {registerMode || emailMode ? (
            <>
              <Field
                label="邮箱地址"
                value={fields.email}
                onChange={(value) => change("email", value)}
                error={errors.email}
                placeholder="用于接收验证码"
                type="email"
                autoComplete="email"
                icon={<Mail size={15} />}
              />
              <div className="code-field">
                <Field
                  label="邮箱验证码"
                  value={fields.code}
                  onChange={(value) => change("code", value)}
                  error={errors.code}
                  placeholder="6 位数字"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                />
                <button
                  type="button"
                  className="code-button"
                  disabled={sending || Boolean(retryAfter)}
                  onClick={() => void sendCode()}
                >
                  {sending ? (
                    <LoaderCircle size={14} className="spin" />
                  ) : retryAfter ? (
                    `${retryAfter}s 后重发`
                  ) : (
                    "获取验证码"
                  )}
                </button>
              </div>
            </>
          ) : null}
          {(!emailMode || registerMode) && (
            <Field
              label="密码"
              value={fields.password}
              onChange={(value) => change("password", value)}
              error={errors.password}
              placeholder={registerMode ? "至少 8 个字符" : "输入密码"}
              type="password"
              autoComplete={registerMode ? "new-password" : "current-password"}
            />
          )}
          {error && (
            <div className="auth-error" role="alert">
              {error}
            </div>
          )}
          <button className="auth-submit" disabled={busy} type="submit">
            {busy ? (
              <LoaderCircle size={17} className="spin" />
            ) : (
              <>
                {registerMode ? "创建账号" : "登录"}
                <ArrowRight size={16} />
              </>
            )}
          </button>
        </form>
        {registerMode ? (
          <div className="auth-switch">
            已有账号？
            <button onClick={() => switchMode("password")}>返回登录</button>
          </div>
        ) : (
          <div className="auth-switch">
            还没有账号？
            <button onClick={() => switchMode("register")}>创建账号</button>
          </div>
        )}
        <div className="auth-trust">
          <ShieldCheck size={14} />
          邮箱验证码会发送到你的邮箱{" "}
          <a href="http://127.0.0.1:8025" target="_blank" rel="noreferrer">
            打开测试邮箱
          </a>
        </div>
      </section>
    </main>
  );
}
function Field({
  label,
  value,
  onChange,
  error,
  placeholder,
  type = "text",
  autoComplete,
  inputMode,
  icon,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  error?: string;
  placeholder?: string;
  type?: string;
  autoComplete?: string;
  inputMode?: "numeric";
  icon?: ReactNode;
}) {
  return (
    <label className={`auth-field ${error ? "has-error" : ""}`}>
      <span>{label}</span>
      <div className="auth-input-wrap">
        {icon}
        {
          <input
            value={value}
            type={type}
            placeholder={placeholder}
            autoComplete={autoComplete}
            inputMode={inputMode}
            onChange={(event) => onChange(event.target.value)}
          />
        }
      </div>
      {error && <small>{error}</small>}
    </label>
  );
}
