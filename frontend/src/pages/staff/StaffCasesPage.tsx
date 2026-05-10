import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { staffCases } from '../../api/casesApi';
import AppLayout from '../../components/layout/AppLayout';
import ServerState from '../../components/ui/ServerState';

const itemsFrom = (data: any) => data?.items || data || [];

export default function StaffCasesPage() {
  const { data, error, isLoading } = useQuery({ queryKey: ['staffCases'], queryFn: async () => (await staffCases()).data, retry: false });
  const items = itemsFrom(data);
  return (
    <AppLayout>
      <div className="case-actions">
        <h1>Мои дела</h1>
        <Link to="/staff/cases/create" className="button">Создать дело</Link>
      </div>
      <p className="status-warning">В этом списке показываются все ваши дела, включая черновики. Публичный поиск отображает только опубликованные документы.</p>
      <ServerState loading={isLoading} error={error} />
      {(error as any)?.response?.status === 404 && <p className="warning-message">Backend пока не возвращает список дел работника суда.</p>}
      <div className="case-list">
        {items.map((c: any) => (
          <article className="card" key={c.id}>
            <h3>{c.case_number}</h3>
            <p><b>Статус:</b> <span className="badge">{c.status || '—'}</span></p>
            <Link className="button button-secondary" to={`/staff/cases/${c.id}`}>Открыть дело</Link>
          </article>
        ))}
      </div>
    </AppLayout>
  );
}
