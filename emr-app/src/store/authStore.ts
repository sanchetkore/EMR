import { create } from 'zustand';

interface User {
  id: number;
  username: string;
  email: string;
  role_id: number | null;
}

interface AuthState {
  user: User | null;
  token: string | null;
  refreshToken: string | null;
  isLoading: boolean;
  setAuth: (user: User, token: string, refreshToken: string) => void;
  updateTokens: (token: string, refreshToken: string) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  token: null,
  refreshToken: null,
  isLoading: false,
  setAuth: (user, token, refreshToken) => set({ user, token, refreshToken }),
  updateTokens: (token, refreshToken) => set({ token, refreshToken }),
  logout: () => set({ user: null, token: null, refreshToken: null }),
}));
