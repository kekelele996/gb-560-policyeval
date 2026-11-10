import { redirect } from 'react-router-dom';
import { tokenStore } from '../api/client';

/** 路由守卫：无 token 直接回登录页（后端仍会校验 JWT）。 */
export const requireAuth = () => {
  if (!tokenStore.get()) {
    return redirect('/login');
  }
  return null;
};
