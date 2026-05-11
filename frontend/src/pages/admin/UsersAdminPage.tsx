import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import AppLayout from '../../components/layout/AppLayout';
import { assignRoles, listUsers } from '../../api/authApi';
import ServerState from '../../components/ui/ServerState';
import type { Role } from '../../api/types';

const ROLES: Role[] = ['REGISTERED_USER', 'COURT_STAFF', 'JUDGE', 'COURT_CLERK', 'ADMIN'];
const ROLE_LABELS: Record<Role, string> = {
  REGISTERED_USER: 'Зарегистрированный пользователь',
  COURT_STAFF: 'Работник суда',
  JUDGE: 'Судья',
  COURT_CLERK: 'Секретарь суда',
  ADMIN: 'Администратор'
};
const saveErrorMessage = (er: any) => {
  const status = er?.response?.status;
  if (status === 403) return 'Недостаточно прав';
  if (status === 404) return 'Пользователь не найден';
  if (status >= 500) return 'Внутренняя ошибка сервера';
  return 'Не удалось обновить роль пользователя';
};

export default function UsersAdminPage() {
  const [roleByUserId, setRoleByUserId] = useState<Record<string, Role>>({});
  const [saving, setSaving] = useState('');
  const [message, setMessage] = useState('');
  const [errorMessage, setErrorMessage] = useState('');
  const { data, error, isLoading, refetch } = useQuery({ queryKey: ['adminUsers'], queryFn: listUsers, retry: false });
  const users = data || [];

  useEffect(() => {
    if (!data) return;
    setRoleByUserId(Object.fromEntries(data.map((u: any) => [u.id, u.role || u.roles?.[0] || 'REGISTERED_USER'])));
  }, [data]);

  const saveRole = async (userId: string) => {
    setSaving(userId);
    setMessage('');
    setErrorMessage('');
    try {
      await assignRoles(userId, roleByUserId[userId] || 'REGISTERED_USER');
      setMessage('Роль пользователя обновлена.');
      await refetch();
    } catch (er: any) {
      setErrorMessage(saveErrorMessage(er));
    } finally {
      setSaving('');
    }
  };

  return (
    <AppLayout>
      <h1>Управление пользователями</h1>
      <ServerState loading={isLoading} error={error} />
      {(error as any)?.response?.status === 404 && <p className='warning-message'>Backend пока не поддерживает управление пользователями.</p>}
      {message && <p className='success-message'>{message}</p>}
      {errorMessage && <p className='error-message'>{errorMessage}</p>}
      {users.map((u: any) => <div className='user-card' key={u.id}>
        <div><h3>{u.username}</h3><p>{u.email || 'Email не указан'}</p></div>
        <label>Роль пользователя</label>
        <select className='role-select' value={roleByUserId[u.id] || 'REGISTERED_USER'} onChange={(e) => setRoleByUserId((prev) => ({ ...prev, [u.id]: e.target.value as Role }))}>
          {ROLES.map((r) => <option key={r} value={r}>{ROLE_LABELS[r]}</option>)}
        </select>
        <div className='admin-card-actions'><button className='button' disabled={saving === u.id} onClick={() => saveRole(u.id)}>{saving === u.id ? 'Сохранение...' : 'Сохранить роль'}</button></div>
      </div>)}
    </AppLayout>
  );
}
