import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import AppLayout from '../../components/layout/AppLayout';
import { getSystemHealth } from '../../api/adminApi';
import LoadingSpinner from '../../components/ui/LoadingSpinner';

const SERVICES = ['auth-service', 'case-service', 'ner-service', 'anonymization-service'];
const statusLabel: Record<string, string> = { ok: 'работает', unavailable: 'недоступен', unknown: 'неизвестно' };
const statusClass = (status: string) => status === 'ok' ? 'badge badge-ok' : status === 'unavailable' ? 'badge badge-error' : 'badge badge-warning';

export default function AdminDashboardPage() {
  const { data, error, isLoading } = useQuery({ queryKey: ['systemHealth'], queryFn: async () => (await getSystemHealth()).data, retry: false });
  const services = data?.services || [];
  const byName = new Map(services.map((s: any) => [s.name, s.status || 'unknown']));
  const notImplemented = (error as any)?.response?.status === 404;

  return (
    <AppLayout>
      <h1>Админ-панель</h1>
      <div className='admin-grid'>
        <div className='admin-card'>
          <h3>Пользователи</h3>
          <p>Просмотр пользователей и изменение ролей</p>
          <div className='admin-card-actions'><Link to='/admin/users' className='button'>Управление пользователями</Link></div>
        </div>
        <div className='admin-card'>
          <h3>Справочник судов</h3>
          <p>Добавление и редактирование судов</p>
          <div className='admin-card-actions'><Link to='/admin/courts' className='button'>Управление судами</Link></div>
        </div>
        <div className='admin-card'>
          <h3>Журнал аудита</h3>
          <p>Просмотр событий доступа и административных действий</p>
          <div className='admin-card-actions'><Link to='/admin/audit' className='button'>Открыть аудит</Link></div>
        </div>
        <div className='admin-card'>
          <h3>Состояние сервисов</h3>
          <p>Статус auth-service, case-service, ner-service, anonymization-service</p>
          {isLoading && <div className='server-state'><LoadingSpinner /><span>Загрузка...</span></div>}
          {notImplemented && <p className='warning-message'>Проверка состояния сервисов пока не реализована на backend.</p>}
          {!isLoading && !notImplemented && SERVICES.map((name) => {
            const status = String(byName.get(name) || 'unknown');
            return <p key={name} className='service-row'><span>{name}:</span> <span className={statusClass(status)}>{statusLabel[status] || statusLabel.unknown}</span></p>;
          })}
        </div>
      </div>
    </AppLayout>
  );
}
