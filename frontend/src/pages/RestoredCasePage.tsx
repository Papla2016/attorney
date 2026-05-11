import { Link, useParams } from 'react-router-dom';
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

  return <AppLayout>
    <h1>Восстановленные данные дела</h1>
    <p className='warning-banner'>Внимание: отображаются персональные данные. Доступ к просмотру фиксируется в журнале аудита.</p>
    <ServerState loading={isLoading} error={status === 403 || status === 404 ? null : error} />
    {status === 403 && <p className='error-message'>У вас нет доступа к восстановленным данным этого дела.</p>}{status === 404 && <p className='error-message'>Дело не найдено.</p>}
    {!isLoading && !error && c && <>
      <div className='case-card'><h2>Основные сведения дела</h2><div className='case-meta-grid'><p><b>Номер дела:</b> {val(c.case_number)}</p><p><b>Номер документа:</b> {val(c.document_number)}</p><p><b>Суд:</b> {val(c.court_name || c.court)}</p><p><b>Регион:</b> {val(c.region)}</p><p><b>Дата документа:</b> {val(c.document_date)}</p><p><b>Статус:</b> {val(c.status)}</p></div></div>
      {documents.map((d: any) => { const mappings = list(d.entity_mappings || d.mappings); const id = d.id || d.document_id; return <div className='case-card' key={id}>
        <div className='case-actions'><h2>{val(d.title)}</h2>{id ? <Link className='button button-secondary' to={`/staff/documents/${id}/anonymization`}>Перейти к ручной проверке обезличивания</Link> : <Link className='button button-secondary' to={`/staff/cases/${caseId}/upload`}>Перейти к ручной проверке обезличивания</Link>}</div>
        <h3>Исходный текст</h3><CourtDocumentView caseData={c} document={d} text={d.original_text} restored />
        <h3>Обезличенный текст</h3><div className='court-document-text anonymized-block'>{val(d.anonymized_text)}</div>
        <h3>Таблица соответствия</h3>
        {mappings.length === 0 && <p className='empty-state'>Таблица соответствия пуста. Возможно, документ был создан до ручного обезличивания или backend не вернул mappings.</p>}
        {mappings.length > 0 && <div className='table-card'><table className='mapping-table'><thead><tr><th>placeholder</th><th>исходное значение</th><th>тип сущности</th><th>источник</th></tr></thead><tbody>{mappings.map((m: any, idx: number) => <tr key={`${m.placeholder}-${idx}`}><td>{val(m.placeholder)}</td><td>{val(m.original_value || m.value)}</td><td>{val(m.entity_type || m.type)}</td><td>{val(m.source)}</td></tr>)}</tbody></table></div>}
      </div>; })}
    </>}
  </AppLayout>;
}
