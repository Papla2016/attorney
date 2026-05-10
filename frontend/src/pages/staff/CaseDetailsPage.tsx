import { useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import AppLayout from '../../components/layout/AppLayout';
import ServerState from '../../components/ui/ServerState';
import { caseDetails, publishDocument, updateCaseStatus } from '../../api/casesApi';
import CourtDocumentView from '../../components/documents/CourtDocumentView';
import { useAuth } from '../../auth/useAuth';
import { isStaff } from '../../utils/roles';

type CaseStatus = 'DRAFT' | 'PUBLISHED' | 'ARCHIVED';

const val = (v: any) => v || '—';
const asList = (v: any) => (Array.isArray(v) ? v : []);
const docId = (d: any) => d.id || d.document_id;
const statusUpper = (v: any) => String(v || '').toUpperCase();
const canPublishStatus = (v: any) => ['DRAFT', 'ANONYMIZED'].includes(statusUpper(v));

const publishErrorMessage = (error: any) => {
  const status = error?.response?.status;
  if (status === 403) return 'Недостаточно прав для публикации';
  if (status === 400) return 'Документ ещё не готов к публикации';
  if (status >= 500) return 'Внутренняя ошибка сервера';
  return 'Не удалось опубликовать документ';
};

const statusErrorMessage = (error: any) => {
  const status = error?.response?.status;
  if (status === 404 || status === 405) return 'Изменение статуса дела пока не реализовано на backend.';
  if (status === 403) return 'Недостаточно прав для изменения статуса дела';
  if (status >= 500) return 'Внутренняя ошибка сервера';
  return 'Не удалось обновить статус дела';
};

export default function CaseDetailsPage() {
  const { caseId = '' } = useParams();
  const queryClient = useQueryClient();
  const { roles, isAuthenticated } = useAuth();
  const canManage = isStaff(roles);
  const [caseStatus, setCaseStatus] = useState<CaseStatus>('DRAFT');
  const [message, setMessage] = useState('');
  const [actionError, setActionError] = useState('');

  const { data, error, isLoading } = useQuery({
    queryKey: ['caseDetails', caseId],
    queryFn: async () => (await caseDetails(caseId)).data,
    retry: false,
  });
  const status = (error as any)?.response?.status;
  const c = data?.case || data;
  const documents = asList(c?.documents || data?.documents);
  const judges = asList(c?.judge_names || c?.judges);
  const participants = asList(c?.participants);
  const currentCaseStatus = statusUpper(c?.status) || 'DRAFT';

  useEffect(() => {
    if (c?.status && ['DRAFT', 'PUBLISHED', 'ARCHIVED'].includes(statusUpper(c.status))) {
      setCaseStatus(statusUpper(c.status) as CaseStatus);
    }
  }, [c?.status]);

  const refetchCase = async () => {
    await queryClient.invalidateQueries({ queryKey: ['caseDetails', caseId] });
  };

  const publishMutation = useMutation({
    mutationFn: (documentId: string) => publishDocument(documentId),
    onSuccess: async () => {
      setActionError('');
      setMessage('Документ опубликован.');
      await refetchCase();
    },
    onError: (err) => {
      setMessage('');
      setActionError(publishErrorMessage(err));
    },
  });

  const statusMutation = useMutation({
    mutationFn: () => updateCaseStatus(caseId, caseStatus),
    onSuccess: async () => {
      setActionError('');
      setMessage('Статус дела обновлён.');
      await refetchCase();
    },
    onError: (err) => {
      setMessage('');
      setActionError(statusErrorMessage(err));
    },
  });

  const caseInfo = useMemo(() => ({
    case_number: c?.case_number,
    document_number: c?.document_number,
    court_name: c?.court_name || c?.court,
    region: c?.region,
    document_date: c?.document_date,
    legal_article: c?.legal_article || c?.law_article,
    judge_names: judges,
  }), [c, judges]);

  return (
    <AppLayout>
      <ServerState loading={isLoading} error={status === 403 || status === 404 ? null : error} />
      {status === 404 && <p className="error-message">Дело не найдено.</p>}
      {status === 403 && <p className="error-message">Недостаточно прав для просмотра дела.</p>}
      {!isLoading && !error && c && (
        <>
          <div className="case-actions">
            <h1>Дело № {val(c.case_number)}</h1>
            {canManage && <Link className="button" to={`/staff/cases/${caseId}/upload`}>Загрузить документ</Link>}
          </div>
          {message && <p className="success-message">{message}</p>}
          {actionError && <p className="error-message">{actionError}</p>}

          {currentCaseStatus === 'DRAFT' && (
            <p className="status-warning">
              Дело находится в черновике. Оно не отображается в публичном поиске, пока документ не будет обезличен и опубликован.
            </p>
          )}

          <section className="status-panel">
            <div>
              <h2>Статус дела</h2>
              <p>Публичный поиск показывает только опубликованные документы. Дело в статусе DRAFT не отображается публичным пользователям.</p>
              {currentCaseStatus === 'DRAFT' && <p>Дело не отображается в публичном поиске, потому что оно ещё не опубликовано.</p>}
            </div>
            {canManage ? (
              <div className="status-controls">
                <select value={caseStatus} onChange={(event) => setCaseStatus(event.target.value as CaseStatus)}>
                  <option value="DRAFT">Черновик</option>
                  <option value="PUBLISHED">Опубликовано</option>
                  <option value="ARCHIVED">Архивировано</option>
                </select>
                <button type="button" onClick={() => statusMutation.mutate()} disabled={statusMutation.isPending}>Сохранить статус</button>
              </div>
            ) : (
              <span className="badge">{val(c.status)}</span>
            )}
          </section>

          <section className="case-card">
            <h2>Основные сведения</h2>
            <div className="case-meta-grid">
              <p><b>Номер дела:</b> {val(c.case_number)}</p>
              <p><b>Номер документа:</b> {val(c.document_number)}</p>
              <p><b>Дата документа:</b> {val(c.document_date)}</p>
              <p><b>Суд:</b> {val(c.court_name || c.court)}</p>
              <p><b>Регион:</b> {val(c.region)}</p>
              <p><b>Инстанция:</b> {val(c.instance)}</p>
              <p><b>Статья закона:</b> {val(c.legal_article || c.law_article)}</p>
              <p><b>Судебная практика:</b> {val(c.judicial_practice || c.practice_topic)}</p>
              <p><b>Статус дела:</b> <span className="badge">{val(c.status)}</span></p>
            </div>
          </section>

          <section className="case-card">
            <h2>Состав суда</h2>
            {judges.length ? <ul>{judges.map((j: any) => <li key={j}>{j}</li>)}</ul> : <p>Судьи дела не указаны.</p>}
          </section>

          <section className="case-card">
            <h2>Участники дела</h2>
            {participants.length ? (
              <div className="case-meta-grid">
                {participants.map((p: any, idx: number) => <p key={p.id || idx}><b>{val(p.role)}:</b> {val(p.display_name || p.name || p.username)}</p>)}
              </div>
            ) : <p>Участники дела не указаны.</p>}
          </section>

          <section className="case-card">
            <h2>Документы дела</h2>
            {documents.length ? documents.map((d: any) => {
              const id = docId(d);
              const documentStatus = statusUpper(d.status);
              return (
                <article className="document-card" key={id}>
                  <div className="document-card-header">
                    <div>
                      <h3>{val(d.title)}</h3>
                      <p><b>Тип судебного акта:</b> {val(d.act_type || d.document_type)}</p>
                      <p><b>Статус:</b> <span className="badge">{val(d.status)}</span></p>
                      <p><b>Дата:</b> {val(d.document_date || d.date || c.document_date)}</p>
                    </div>
                  </div>
                  {['DRAFT', 'ANONYMIZED'].includes(documentStatus) && (
                    <p className="status-warning">Документ ещё не опубликован. Публичные пользователи его не увидят.</p>
                  )}
                  <div className="case-actions">
                    {id && <Link className="button" to={`/documents/${id}`}>Открыть публичную версию</Link>}
                    {isAuthenticated && (d.can_view_restored || c.can_view_restored || canManage) && <Link className="button button-secondary" to={`/cases/${caseId}/restored`}>Восстановленные данные</Link>}
                    {canManage && canPublishStatus(d.status) && id && (
                      <button type="button" onClick={() => publishMutation.mutate(id)} disabled={publishMutation.isPending}>Опубликовать документ</button>
                    )}
                  </div>
                  <CourtDocumentView title={d.title} text={d.anonymized_text || d.text || d.content || d.public_text || d.full_text} caseInfo={caseInfo} />
                </article>
              );
            }) : (
              <div className="empty-state">
                <p>Документы пока не загружены.</p>
                {canManage && <Link className="button" to={`/staff/cases/${caseId}/upload`}>Загрузить документ</Link>}
              </div>
            )}
          </section>
        </>
      )}
    </AppLayout>
  );
}
