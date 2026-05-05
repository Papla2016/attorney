import { useQuery } from '@tanstack/react-query';
import AppLayout from '../../components/layout/AppLayout';
import { assignRoles, listUsers } from '../../api/authApi';
import { useState } from 'react';
import ServerState from '../../components/ui/ServerState';
const ROLES=['REGISTERED_USER','COURT_STAFF','JUDGE','COURT_CLERK','ADMIN'];
export default function UsersAdminPage(){ const [saving,setSaving]=useState<string>(''); const {data,error,isLoading,refetch}=useQuery({queryKey:['adminUsers'],queryFn:listUsers,retry:false}); const users=data||[]; return <AppLayout><h1>Управление пользователями</h1><ServerState loading={isLoading} error={error}/>{(error as any)?.response?.status===404&&<p>Backend пока не поддерживает управление пользователями.</p>}
{users.map((u:any)=><div className='card' key={u.id}><p>{u.username}</p><p>{u.email}</p><div className='form-row'>{ROLES.map((r)=><label key={r}><input type='checkbox' checked={u.roles?.includes(r)} onChange={(e)=>{u.roles=e.target.checked?[...(u.roles||[]),r]:(u.roles||[]).filter((x:string)=>x!==r); refetch();}}/>{r}</label>)}</div><button className='button' disabled={saving===u.id} onClick={async()=>{setSaving(u.id);await assignRoles(u.id,u.roles||[]);setSaving('');}}>Сохранить роли</button></div>)}</AppLayout>;}
