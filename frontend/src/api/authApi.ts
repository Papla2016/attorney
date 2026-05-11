import { client } from './client';
import type { User } from './types';

export const login = (username: string, password: string) => client.post('/auth/login', { username, password });
export const register = (payload: { username: string; email: string; password: string }) => client.post('/auth/register', payload);
export const me = async (): Promise<User> => (await client.get('/auth/me')).data;
export const updateMe = (payload: { username?: string; email?: string }) => client.patch('/auth/me', payload);
export const changePassword = (payload: { current_password: string; new_password: string }) => client.post('/auth/me/change-password', payload);
export const listUsers = async (): Promise<User[]> => (await client.get('/auth/users')).data;
export const assignRoles = (userId: string, role: string) => client.post(`/auth/users/${userId}/roles`, { role, roles: [role] });
