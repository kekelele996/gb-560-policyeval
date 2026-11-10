import { api } from './client';
import type { Role, User } from '../types/models';

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  user: User;
  permissions: string[];
}

export const authApi = {
  login: (email: string, password: string) =>
    api.postAnonymous<LoginResponse>('/auth/login', { email, password }),
  me: () => api.get<User & { permissions: string[] }>('/auth/me'),
  roleLabel: (role: Role): string => role,
};
