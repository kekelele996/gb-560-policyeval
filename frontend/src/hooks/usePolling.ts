import { useEffect, useRef } from 'react';

/** 轮询 hook：当 enabled 为 true 时每 intervalMs 执行一次 callback。
 *  用于评估运行（status=running）时前端实时刷新状态。 */
export const usePolling = (callback: () => void, enabled: boolean, intervalMs = 1500) => {
  const saved = useRef(callback);
  saved.current = callback;

  useEffect(() => {
    if (!enabled) return undefined;
    const timer = window.setInterval(() => saved.current(), intervalMs);
    return () => window.clearInterval(timer);
  }, [enabled, intervalMs]);
};
