import { Navigate, Outlet } from 'react-router-dom';
import { useAuth } from './useAuth';
import { hasAnyRole } from '../utils/roles';
import type { Role } from '../api/types';
export default function RequireRole({ roles }: { roles: Role[] }) { const {roles:userRoles}=useAuth(); return hasAnyRole(userRoles, roles)?<Outlet/>:<Navigate to='/' replace/>; }
