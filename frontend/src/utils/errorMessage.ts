import { ApiError } from '../types/api';

export const errorMessage = (error: unknown): string => {
  if (error instanceof ApiError) {
    if (error.code === 'DSL_PARSE_ERROR') {
      const nested = error.extra as { error?: { message?: string; line?: number; column?: number } };
      if (nested?.error?.message) {
        return `DSL 解析失败：${nested.error.message}（第 ${nested.error.line} 行第 ${nested.error.column} 列）`;
      }
    }
    return error.detail ? `${error.message}（${error.detail}）` : error.message;
  }
  if (error instanceof Error) return error.message;
  return '请求失败，请稍后重试';
};
