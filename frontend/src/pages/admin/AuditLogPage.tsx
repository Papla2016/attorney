import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import AppLayout from '../../components/layout/AppLayout';
import { getAuditLog, type AuditLogParams } from '../../api/adminApi';
import ServerState from '../../components/ui/ServerState';

const ACTION_LABELS: Record<string, string> = {
  VIEW_RESTORED_CASE: 'Просмотр восстановленных данных',
  CREATE_CASE: 'Создание дела',
  UPLOAD_DOCUMENT: 'Загрузка документа',
  PUBLISH_DOCUMENT: 'Публикация документа',
  UPDATE_ROLES: 'Изменение ролей'
};
const actionLabel = (v: string) => ACTION_LABELS[v] || v || '—';
const formatDetails = (details: any) => typeof details === 'string' ? details : details ? JSON.stringify(details) : '—';

export default function AuditLogPage() {
  const [filters, setFilters] = useState<AuditLogParams>({});
  const { data, error, isLoading, refetch } = useQuery({ queryKey: ['auditLog', filters], queryFn: async () => (await getAuditLog(filters)).data, retry: false });
  const rows = data?.items || data || [];
  const notImplemented = (error as any)?.response?.status === 404;
  const updateFilter = (name: keyof AuditLogParams, value: string) => setFilters((prev) => ({ ...prev, [name]: value || undefined }));

  return (
    <AppLayout>
      <h1>Журнал аудита</h1>
      <div className='card form-card'>
        <h3>Фильтры</h3>
        <form onSubmit={(e) => { e.preventDefault(); refetch(); }}>
          <div className='form-grid'>
            <label>Действие<select value={filters.action || ''} onChange={(e) => updateFilter('action', e.target.value)}><option value=''>Все действия</option>{Object.entries(ACTION_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
            <label>Пользователь<input value={filters.user || ''} onChange={(e) => updateFilter('user', e.target.value)} /></label>
            <label>Тип ресурса<input value={filters.resource_type || ''} onChange={(e) => updateFilter('resource_type', e.target.value)} /></label>
            <label>Дата от<input type='date' value={filters.date_from || ''} onChange={(e) => updateFilter('date_from', e.target.value)} /></label>
            <label>Дата до<input type='date' value={filters.date_to || ''} onChange={(e) => updateFilter('date_to', e.target.value)} /></label>
          </div>
          <button className='button'>Применить фильтры</button>
        </form>
      </div>
      <ServerState loading={isLoading} error={notImplemented ? null : error} />
      {notImplemented && <p className='warning-message'>Backend пока не поддерживает журнал аудита.</p>}
      {!notImplemented && <div className='card table-card'><table className='audit-table'><thead><tr><th>Дата и время</th><th>Пользователь</th><th>Действие</th><th>Тип ресурса</th><th>ID ресурса</th><th>Детали</th></tr></thead><tbody>
        {rows.map((row: any) => <tr key={row.id || `${row.created_at}-${row.resource_id}`}><td>{row.created_at || row.timestamp || row.datetime || '—'}</td><td>{row.username || row.user || row.user_id || '—'}</td><td>{actionLabel(row.action)}</td><td>{row.resource_type || '—'}</td><td>{row.resource_id || '—'}</td><td>{formatDetails(row.details)}</td></tr>)}
        {!isLoading && rows.length === 0 && <tr><td colSpan={6}>Событий аудита пока нет.</td></tr>}
      </tbody></table></div>}
    </AppLayout>
  );
}
