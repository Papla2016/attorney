import { useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import AppLayout from '../components/layout/AppLayout';
import ServerState from '../components/ui/ServerState';
import { restoredCase } from '../api/casesApi';
import CourtDocumentView from '../components/documents/CourtDocumentView';

const val = (v: any) => v || '—';
const list = (v: any) => Array.isArray(v) ? v : [];

export default function RestoredCasePage() {
  const { caseId = '' } = useParams();
  const { data, error, isLoading } = useQuery({ queryKey: ['restoredCase', caseId], queryFn: async () => (await restoredCase(caseId)).data, retry: false });
  const status = (error as any)?.response?.status;
  const c = data?.case || data;
  const documents = list(c?.documents || data?.documents);

  return (
    <AppLayout>
      <h1>Восстановленные данные дела</h1>
      <p className='warning-banner'>Внимание: отображаются персональные данные. Доступ к просмотру фиксируется в журнале аудита.</p>
      <ServerState loading={isLoading} error={status === 403 || status === 404 ? null : error} />
      {status === 403 && <p className='error-message'>У вас нет доступа к восстановленным данным этого дела.</p>}
      {status === 404 && <p className='error-message'>Дело не найдено.</p>}
      {!isLoading && !error && c && <>
        <div className='case-card'><h2>Основные сведения дела</h2><div className='case-meta-grid'><p><b>Номер дела:</b> {val(c.case_number)}</p><p><b>Номер документа:</b> {val(c.document_number)}</p><p><b>Суд:</b> {val(c.court_name || c.court)}</p><p><b>Регион:</b> {val(c.region)}</p><p><b>Дата документа:</b> {val(c.document_date)}</p><p><b>Статус:</b> {val(c.status)}</p></div></div>
        {documents.map((d: any) => <div className='case-card' key={d.id || d.document_id}>
          <h2>{val(d.title)}</h2>
          <h3>Исходный текст</h3><CourtDocumentView caseData={c} document={d} text={d.original_text} restored />
          <h3>Обезличенный текст</h3><div className='court-document-text anonymized-block'>{val(d.anonymized_text)}</div>
          <h3>Таблица соответствия</h3>
          <div className='table-card'><table className='audit-table'><thead><tr><th>placeholder</th><th>исходное значение</th><th>тип сущности</th></tr></thead><tbody>
            {list(d.entity_mappings || d.mappings).map((m: any, idx: number) => <tr key={`${m.placeholder}-${idx}`}><td>{val(m.placeholder)}</td><td>{val(m.original_value || m.value)}</td><td>{val(m.entity_type || m.type)}</td></tr>)}
            {list(d.entity_mappings || d.mappings).length === 0 && <tr><td colSpan={3}>Соответствия не найдены.</td></tr>}
          </tbody></table></div>
        </div>)}
      </>}
    </AppLayout>
  );
}
