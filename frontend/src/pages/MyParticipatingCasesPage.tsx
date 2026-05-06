import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import AppLayout from '../components/layout/AppLayout';
import ServerState from '../components/ui/ServerState';
import { participatingCases } from '../api/casesApi';

const val = (v: any) => v || '—';

export default function MyParticipatingCasesPage() {
  const { data, error, isLoading } = useQuery({ queryKey: ['participatingCases'], queryFn: async () => (await participatingCases()).data, retry: false });
  const cases = data?.items || data || [];
  const networkError = (error as any)?.message === 'Network Error';

  return (
    <AppLayout>
      <h1>Мои дела</h1>
      {networkError ? <p className='error-message'>Сервер недоступен. Не удалось загрузить ваши дела.</p> : <ServerState loading={isLoading} error={error} />}
      {!isLoading && !error && cases.length === 0 && <p>У вас пока нет дел, в которых вы указаны участником.</p>}
      <div className='case-list'>
        {cases.map((c: any) => <div className='case-card' key={c.id || c.case_id}>
          <h3>Дело № {val(c.case_number)}</h3>
          <div className='case-meta-grid'>
            <p><b>Номер документа:</b> {val(c.document_number)}</p><p><b>Суд:</b> {val(c.court_name || c.court)}</p><p><b>Регион:</b> {val(c.region)}</p><p><b>Дата документа:</b> {val(c.document_date)}</p><p><b>Инстанция:</b> {val(c.instance)}</p><p><b>Статья закона:</b> {val(c.legal_article || c.law_article)}</p><p><b>Роль в деле:</b> {val(c.user_role || c.role)}</p><p><b>Статус:</b> {val(c.status)}</p>
          </div>
          <div className='admin-card-actions'><Link className='button' to={`/cases/${c.id || c.case_id}`}>Открыть дело</Link>{c.can_view_restored && <Link className='button button-secondary' to={`/cases/${c.id || c.case_id}/restored`}>Восстановленные данные</Link>}</div>
        </div>)}
      </div>
    </AppLayout>
  );
}
