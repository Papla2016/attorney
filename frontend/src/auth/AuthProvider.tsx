import { createContext, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import type { Role, User } from '../api/types';
import * as authApi from '../api/authApi';

type AuthCtx = { user: User | null; roles: Role[]; isAuthenticated: boolean; isLoading: boolean; login: (u:string,p:string)=>Promise<void>; logout: ()=>void; refresh: ()=>Promise<void>; };
export const AuthContext = createContext<AuthCtx | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setLoading] = useState(true);
  const refresh = async () => {
    if (!localStorage.getItem('access_token')) return setLoading(false);
    try { setUser(await authApi.me()); } catch { localStorage.removeItem('access_token'); setUser(null);} finally { setLoading(false); }
  };
  useEffect(() => { refresh(); }, []);
  const login = async (username:string, password:string) => { const r = await authApi.login(username,password); localStorage.setItem('access_token', r.data.access_token); await refresh(); };
  const logout = () => { localStorage.removeItem('access_token'); setUser(null); };
  const value = useMemo(() => ({ user, roles: user?.role ? [user.role] : (user?.roles || []), isAuthenticated: !!user, isLoading, login, logout, refresh }), [user, isLoading]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
