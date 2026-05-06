import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import AppLayout from '../../components/layout/AppLayout';
import ServerState from '../../components/ui/ServerState';
import { getSystemHealth } from '../../api/adminApi';

function statusLabel(status: string) {
  if (status === 'ok') return 'работает';
  if (status === 'unavailable') return 'недоступен';
  return 'неизвестно';
}

export default function AdminDashboardPage() {
  const { data, error, isLoading } = useQuery({ queryKey: ['systemHealth'], queryFn: getSystemHealth, retry: false });
  const services = data?.data?.services || [];

  return (
    <AppLayout>
      <h1>Админ-панель</h1>
      <div className='admin-grid'>
        <div className='admin-card'>
          <h3>Пользователи</h3>
          <p>Просмотр пользователей и изменение ролей.</p>
          <div className='admin-card-actions'><Link to='/admin/users' className='button'>Управление пользователями</Link></div>
        </div>
        <div className='admin-card'>
          <h3>Справочник судов</h3>
          <p>Добавление и редактирование судов общей юрисдикции.</p>
          <div className='admin-card-actions'><Link to='/admin/courts' className='button'>Управление судами</Link></div>
        </div>
        <div className='admin-card'>
          <h3>Журнал аудита</h3>
          <p>Просмотр событий доступа и административных действий.</p>
          <div className='admin-card-actions'><Link to='/admin/audit' className='button'>Открыть аудит</Link></div>
        </div>
        <div className='admin-card'>
          <h3>Состояние сервисов</h3>
          <ServerState loading={isLoading} error={error}/>
          {!isLoading && !error && services.map((s: any) => (
            <p key={s.name}><strong>{s.name}:</strong> <span className={s.status === 'ok' ? 'badge badge-ok' : 'badge badge-error'}>{statusLabel(s.status)}</span></p>
          ))}
          {(error as any)?.response?.status === 404 && <p className='warning-message'>Проверка состояния сервисов пока не реализована на backend.</p>}
        </div>
      </div>
    </AppLayout>
  );
}
