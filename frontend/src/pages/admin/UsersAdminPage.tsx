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
  ADMIN: 'Администратор',
};

export default function UsersAdminPage() {
  const [saving, setSaving] = useState('');
  const [message, setMessage] = useState('');
  const [rolesByUserId, setRolesByUserId] = useState<Record<string, string[]>>({});
  const { data, error, isLoading, refetch } = useQuery({ queryKey: ['adminUsers'], queryFn: listUsers, retry: false });
  const users = data || [];

  useEffect(() => {
    const next: Record<string, string[]> = {};
    users.forEach((u: any) => { next[u.id] = [...(u.roles || [])]; });
    setRolesByUserId(next);
  }, [users.length]);

  function toggleRole(userId: string, role: string, checked: boolean) {
    setRolesByUserId((prev) => {
      const current = prev[userId] || [];
      return { ...prev, [userId]: checked ? Array.from(new Set([...current, role])) : current.filter((r) => r !== role) };
    });
  }

  async function saveRoles(userId: string) {
    setSaving(userId);
    setMessage('');
    try {
      await assignRoles(userId, rolesByUserId[userId] || []);
      setMessage('Роли пользователя обновлены');
      await refetch();
    } finally {
      setSaving('');
    }
  }

  return (
    <AppLayout>
      <h1>Управление пользователями</h1>
      {message && <p className='success-message'>{message}</p>}
      <ServerState loading={isLoading} error={error}/>
      {(error as any)?.response?.status === 404 && <p>Backend пока не поддерживает управление пользователями.</p>}
      {users.map((u: any) => (
        <div className='card user-card' key={u.id}>
          <div>
            <h3>{u.username}</h3>
            <p>{u.email}</p>
          </div>
          <div className='roles-grid'>
            {ROLES.map((r) => (
              <label className='role-checkbox' key={r}>
                <input type='checkbox' checked={(rolesByUserId[u.id] || []).includes(r)} onChange={(e) => toggleRole(u.id, r, e.target.checked)}/>
                <span>{ROLE_LABELS[r]}</span>
              </label>
            ))}
          </div>
          <button className='button' disabled={saving === u.id} onClick={() => saveRoles(u.id)}>
            {saving === u.id ? 'Сохранение...' : 'Сохранить роли'}
          </button>
        </div>
      ))}
    </AppLayout>
  );
}
