export type AuthMode = "password" | "email" | "register";
export interface AuthFields {
  username: string;
  display_name: string;
  password: string;
  email: string;
  code: string;
}
export type AuthErrors = Partial<Record<keyof AuthFields, string>>;
export const normalizeEmail = (email: string) => email.trim().toLowerCase();
export function validateEmail(email: string): string | undefined {
  const normalized = normalizeEmail(email);
  if (!normalized) return "请输入邮箱地址";
  if (normalized.length > 254 || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(normalized))
    return "请输入有效的邮箱地址";
}
export function validateAuth(mode: AuthMode, fields: AuthFields): AuthErrors {
  const errors: AuthErrors = {};
  if (mode !== "email") {
    if (!fields.username.trim()) errors.username = "请输入用户名";
    else if (
      mode === "register" &&
      !/^[A-Za-z0-9_]{3,32}$/.test(fields.username.trim())
    )
      errors.username = "使用 3–32 位英文字母、数字或下划线";
    if (!fields.password) errors.password = "请输入密码";
    else if (
      mode === "register" &&
      (Array.from(fields.password).length < 8 ||
        Array.from(fields.password).length > 128)
    )
      errors.password = "密码长度需要为 8–128 个字符";
  }
  if (mode === "register" && Array.from(fields.display_name.trim()).length > 80)
    errors.display_name = "昵称最多为 80 个字符";
  if (mode !== "password") {
    const emailError = validateEmail(fields.email);
    if (emailError) errors.email = emailError;
    if (!/^\d{6}$/.test(fields.code.trim()))
      errors.code = "请输入邮件中的 6 位数字验证码";
  }
  return errors;
}
