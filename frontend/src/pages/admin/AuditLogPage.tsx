import { useQuery } from '@tanstack/react-query';
import AppLayout from '../../components/layout/AppLayout';
import ServerState from '../../components/ui/ServerState';
import { getAuditLog } from '../../api/adminApi';

const ACTION_LABELS: Record<string, string> = {
  VIEW_RESTORED_CASE: 'Просмотр восстановленных данных',
  CREATE_CASE: 'Создание дела',
  UPLOAD_DOCUMENT: 'Загрузка документа',
  PUBLISH_DOCUMENT: 'Публикация документа',
  UPDATE_ROLES: 'Изменение ролей',
  CREATE_COURT: 'Создание суда',
  UPDATE_COURT: 'Изменение суда',
  DELETE_COURT: 'Удаление суда',
};

export default function AuditLogPage() {
  const { data, error, isLoading } = useQuery({ queryKey: ['auditLog'], queryFn: () => getAuditLog(), retry: false });
  const items = data?.data?.items || [];
  return (
    <AppLayout>
      <h1>Журнал аудита</h1>
      <ServerState loading={isLoading} error={error}/>
      {(error as any)?.response?.status === 404 && <div className='card'>Backend пока не поддерживает журнал аудита.</div>}
      <div className='card'>
        <table className='data-table audit-table'>
          <thead><tr><th>Дата и время</th><th>Пользователь</th><th>Действие</th><th>Ресурс</th><th>ID ресурса</th><th>Детали</th></tr></thead>
          <tbody>
            {items.length === 0 && <tr><td colSpan={6}>Событий аудита пока нет.</td></tr>}
            {items.map((a: any) => <tr key={a.id}><td>{a.created_at}</td><td>{a.user_id || '—'}</td><td>{ACTION_LABELS[a.action] || a.action}</td><td>{a.resource_type}</td><td>{a.resource_id}</td><td><pre>{JSON.stringify(a.details || {}, null, 2)}</pre></td></tr>)}
          </tbody>
        </table>
      </div>
    </AppLayout>
  );
}
