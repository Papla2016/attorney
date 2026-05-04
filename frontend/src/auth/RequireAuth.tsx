import { Navigate, Outlet } from 'react-router-dom';
import { useAuth } from './useAuth';
export default function RequireAuth(){ const {isAuthenticated,isLoading}=useAuth(); if(isLoading) return <p>Загрузка...</p>; return isAuthenticated ? <Outlet/> : <Navigate to='/login' replace/>; }
