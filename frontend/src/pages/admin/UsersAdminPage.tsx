import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import AppLayout from '../../components/layout/AppLayout';
import { assignRoles, listUsers } from '../../api/authApi';
import ServerState from '../../components/ui/ServerState';

const ROLES = ['REGISTERED_USER', 'COURT_STAFF', 'JUDGE', 'COURT_CLERK', 'ADMIN'];
const ROLE_LABELS: Record<string, string> = {
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
  return 'Не удалось обновить роли пользователя';
};

export default function UsersAdminPage() {
  const [rolesByUserId, setRolesByUserId] = useState<Record<string, string[]>>({});
  const [saving, setSaving] = useState('');
  const [message, setMessage] = useState('');
  const [errorMessage, setErrorMessage] = useState('');
  const { data, error, isLoading, refetch } = useQuery({ queryKey: ['adminUsers'], queryFn: listUsers, retry: false });
  const users = data || [];

  useEffect(() => {
    if (!data) return;
    setRolesByUserId(Object.fromEntries(data.map((u: any) => [u.id, [...(u.roles || [])]])));
  }, [data]);

  const toggleRole = (userId: string, role: string, checked: boolean) => {
    setRolesByUserId((prev) => {
      const current = prev[userId] || [];
      return { ...prev, [userId]: checked ? Array.from(new Set([...current, role])) : current.filter((r) => r !== role) };
    });
  };

  const saveRoles = async (userId: string) => {
    setSaving(userId);
    setMessage('');
    setErrorMessage('');
    try {
      await assignRoles(userId, rolesByUserId[userId] || []);
      setMessage('Роли пользователя обновлены');
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
      {users.map((u: any) => {
        const userRoles = rolesByUserId[u.id] || [];
        return <div className='user-card' key={u.id}>
          <div><h3>{u.username}</h3><p>{u.email || 'Email не указан'}</p></div>
          <div className='roles-grid'>{ROLES.map((r) => <label className='role-checkbox' key={r}><input type='checkbox' checked={userRoles.includes(r)} onChange={(e) => toggleRole(u.id, r, e.target.checked)} />{ROLE_LABELS[r]}</label>)}</div>
          <div className='admin-card-actions'><button className='button' disabled={saving === u.id} onClick={() => saveRoles(u.id)}>{saving === u.id ? 'Сохранение...' : 'Сохранить роли'}</button></div>
        </div>;
      })}
    </AppLayout>
  );
}
