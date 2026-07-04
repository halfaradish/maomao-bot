import { create } from "zustand";
import { persist } from "zustand/middleware";

interface AuthState {
  token: string | null;
  user: { qq: string } | null;
  login: (token: string, qq: string) => void;
  logout: () => void;
  setToken: (token: string | null) => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      user: null,
      login: (token, qq) => set({ token, user: { qq } }),
      logout: () => set({ token: null, user: null }),
      setToken: (token) => set({ token }),
    }),
    {
      name: "diting_jwt",
      partialize: (state) => ({ token: state.token, user: state.user }),
    }
  )
);
