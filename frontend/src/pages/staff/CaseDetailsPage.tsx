import { Link, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import AppLayout from '../../components/layout/AppLayout';
import ServerState from '../../components/ui/ServerState';
import { caseDetails } from '../../api/casesApi';
import CourtDocumentView from '../../components/documents/CourtDocumentView';
import { useAuth } from '../../auth/useAuth';
import { isStaff } from '../../utils/roles';

const val = (v: any) => v || '—';
const asList = (v: any) => Array.isArray(v) ? v : [];

export default function CaseDetailsPage() {
  const { caseId = '' } = useParams();
  const { roles } = useAuth();
  const { data, error, isLoading } = useQuery({ queryKey: ['caseDetails', caseId], queryFn: async () => (await caseDetails(caseId)).data, retry: false });
  const status = (error as any)?.response?.status;
  const c = data?.case || data;
  const documents = asList(c?.documents || data?.documents);
  const judges = asList(c?.judge_names || c?.judges);
  const participants = asList(c?.participants);

  return (
    <AppLayout>
      <ServerState loading={isLoading} error={status === 403 || status === 404 ? null : error} />
      {status === 404 && <p className='error-message'>Дело не найдено.</p>}
      {status === 403 && <p className='error-message'>Недостаточно прав для просмотра дела.</p>}
      {!isLoading && !error && c && <>
        <h1>Дело № {val(c.case_number)}</h1>
        <div className='case-card'>
          <h2>Основные сведения</h2>
          <div className='case-meta-grid'>
            <p><b>Номер дела:</b> {val(c.case_number)}</p><p><b>Номер документа:</b> {val(c.document_number)}</p><p><b>Дата документа:</b> {val(c.document_date)}</p><p><b>Суд:</b> {val(c.court_name || c.court)}</p><p><b>Регион:</b> {val(c.region)}</p><p><b>Инстанция:</b> {val(c.instance)}</p><p><b>Статья закона:</b> {val(c.legal_article || c.law_article)}</p><p><b>Судебная практика:</b> {val(c.judicial_practice || c.practice_topic)}</p><p><b>Статус:</b> <span className='badge'>{val(c.status)}</span></p>
          </div>
        </div>
        <div className='case-card'><h2>Состав суда</h2>{judges.length ? <ul>{judges.map((j: any) => <li key={j}>{j}</li>)}</ul> : <p>Судьи дела не указаны.</p>}</div>
        <div className='case-card'><h2>Участники дела</h2>{participants.length ? <div className='case-meta-grid'>{participants.map((p: any, idx: number) => <p key={p.id || idx}><b>{val(p.role)}:</b> {val(p.display_name || p.name || p.username)}</p>)}</div> : <p>Участники дела не указаны.</p>}</div>
        <div className='case-card'><h2>Документы дела</h2>{documents.length ? documents.map((d: any) => <div className='document-panel' key={d.id || d.document_id}>
          <h3>{val(d.title)}</h3>
          <p><b>Тип судебного акта:</b> {val(d.act_type || d.document_type)}</p><p><b>Статус:</b> <span className='badge'>{val(d.status)}</span></p>
          <div className='admin-card-actions'><Link className='button' to={`/documents/${d.id || d.document_id}`}>Открыть обезличенную версию</Link>{(d.can_view_restored || c.can_view_restored) && <Link className='button button-secondary' to={`/cases/${caseId}/restored`}>Восстановленные данные</Link>}{isStaff(roles) && <Link className='button button-secondary' to={`/staff/cases/${caseId}/upload`}>Загрузить документ</Link>}</div>
          <CourtDocumentView caseData={c} document={d} />
        </div>) : <><p>Документы пока не загружены.</p>{isStaff(roles) && <Link className='button' to={`/staff/cases/${caseId}/upload`}>Загрузить документ</Link>}</>}
        </div>
      </>}
    </AppLayout>
  );
}
