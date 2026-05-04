import type { Role } from '../api/types';
export const hasRole = (roles: Role[], role: Role) => roles.includes(role);
export const hasAnyRole = (roles: Role[], needed: Role[]) => needed.some((r) => roles.includes(r));
export const isStaff = (roles: Role[]) => hasAnyRole(roles, ['COURT_STAFF','JUDGE','COURT_CLERK','ADMIN']);
export const isAdmin = (roles: Role[]) => hasRole(roles, 'ADMIN');
