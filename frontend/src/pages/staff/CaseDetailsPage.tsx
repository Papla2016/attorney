import { useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import AppLayout from '../../components/layout/AppLayout';
import ServerState from '../../components/ui/ServerState';
import { caseDetails, deleteCaseDocument, publishDocument, updateCase, updateCaseStatus } from '../../api/casesApi';
import CourtDocumentView from '../../components/documents/CourtDocumentView';
import { useAuth } from '../../auth/useAuth';
import { isStaff } from '../../utils/roles';
import { INSTANCE_OPTIONS } from '../../constants/instances';
import { RUSSIAN_REGIONS } from '../../constants/regions';
import type { PublicationValidationDetails, UpdateCaseRequest } from '../../api/types';

type CaseStatus = 'DRAFT' | 'PUBLISHED' | 'ARCHIVED';
const val = (v: any) => v || '—';
const asList = (v: any) => (Array.isArray(v) ? v : []);
const docId = (d: any) => d.id || d.document_id;
const statusUpper = (v: any) => String(v || '').toUpperCase();
const canPublishStatus = (v: any) => ['DRAFT', 'ANONYMIZED'].includes(statusUpper(v));
const csv = (v: any[]) => v.map((x: any) => typeof x === 'string' ? x : (x.display_name || x.name || x.username || '')).filter(Boolean).join('\n');
const lines = (v: string) => v.split('\n').map((x) => x.trim()).filter(Boolean);

const publishErrorMessage = (error: any) => {
  const status = error?.response?.status;
  const apiError = error?.response?.data?.error;
  const code = apiError?.code;
  const details: PublicationValidationDetails = apiError?.details || {};
  const pendingEntities = details.pending_entity_count ?? details.pending_count ?? 0;
  const pendingMentions = details.pending_mention_count;
  const reviewEntities = details.review_entity_count ?? details.review_count ?? 0;
  const reviewMentions = details.review_mention_count;
  if (status === 409 && code === 'PENDING_REDACTION_REVIEW') {
    const lines = ['Документ нельзя опубликовать: проверка обезличивания не завершена.'];
    if (pendingEntities > 0) lines.push(`Новых необработанных сущностей в изменённом тексте: ${pendingEntities}.`);
    if ((pendingMentions || 0) > 0) lines.push(`Упоминаний новых сущностей: ${pendingMentions}.`);
    if (reviewEntities > 0) lines.push(`Обезличенных сущностей, требующих подтверждения: ${reviewEntities}.`);
    if ((reviewMentions || 0) > 0) lines.push(`Упоминаний, требующих проверки: ${reviewMentions}.`);
    return lines.join(' ');
  }
  if (status === 403) return 'Недостаточно прав для публикации документа.';
  if (status === 400) return apiError?.message || 'Документ ещё не готов к публикации.';
  if (status >= 500) return 'Внутренняя ошибка сервера.';
  return apiError?.message || 'Не удалось опубликовать документ.';
};
const caseEditErrorMessage = (error: any) => {
  const status = error?.response?.status;
  if (status === 403) return 'Недостаточно прав для редактирования дела';
  if (status === 404) return 'Дело не найдено';
  if (status === 400 || status === 422) return 'Проверьте заполнение полей';
  if (status >= 500) return 'Внутренняя ошибка сервера';
  return 'Не удалось обновить дело';
};
const statusErrorMessage = (error: any) => {
  const status = error?.response?.status;
  if (status === 403) return 'Недостаточно прав для изменения статуса дела';
  if (status >= 500) return 'Внутренняя ошибка сервера';
  return 'Не удалось обновить статус дела';
};
const deleteErrorMessage = (error: any) => {
  const status = error?.response?.status;
  if (status === 403) return 'Недостаточно прав для удаления документа';
  if (status === 404) return 'Документ не найден';
  return 'Не удалось удалить документ';
};

export default function CaseDetailsPage() {
  const { caseId = '' } = useParams();
  const queryClient = useQueryClient();
  const { roles, isAuthenticated } = useAuth();
  const canManage = isStaff(roles);
  const [caseStatus, setCaseStatus] = useState<CaseStatus>('DRAFT');
  const [message, setMessage] = useState('');
  const [actionError, setActionError] = useState('');
  const [documentActionErrors, setDocumentActionErrors] = useState<Record<string, string>>({});
  const [isEditing, setIsEditing] = useState(false);
  const [editForm, setEditForm] = useState<UpdateCaseRequest & { judges_text?: string; participants_text?: string }>({});

  const { data, error, isLoading } = useQuery({ queryKey: ['caseDetails', caseId], queryFn: async () => (await caseDetails(caseId)).data, retry: false });
  const status = (error as any)?.response?.status;
  const c = data?.case || data;
  const documents = asList(c?.documents || data?.documents);
  const judges = asList(c?.judge_names || c?.judges);
  const participants = asList(c?.participants);
  const currentCaseStatus = statusUpper(c?.status) || 'DRAFT';

  useEffect(() => {
    if (!c) return;
    if (['DRAFT', 'PUBLISHED', 'ARCHIVED'].includes(statusUpper(c.status))) setCaseStatus(statusUpper(c.status) as CaseStatus);
    setEditForm({ court_id: c.court_id || '', court_name: c.court_name || c.court || '', case_number: c.case_number || '', document_number: c.document_number || '', document_date: c.document_date || '', instance: c.instance || '', region: c.region || '', legal_article: c.legal_article || c.law_article || '', judicial_practice: c.judicial_practice || c.practice_topic || '', judges_text: csv(judges), participants_text: csv(participants) });
  }, [c?.id, c?.case_number]);

  const refetchCase = async () => { await queryClient.invalidateQueries({ queryKey: ['caseDetails', caseId] }); };
  const publishMutation = useMutation({ mutationFn: (documentId: string) => publishDocument(documentId), onSuccess: async (_, documentId) => { setActionError(''); setDocumentActionErrors((p)=>({ ...p, [documentId]: '' })); setMessage('Документ опубликован.'); await refetchCase(); }, onError: (err, documentId) => { setMessage(''); const msg = publishErrorMessage(err); setActionError(msg); setDocumentActionErrors((p)=>({ ...p, [documentId]: msg })); } });
  const statusMutation = useMutation({ mutationFn: () => updateCaseStatus(caseId, caseStatus), onSuccess: async () => { setActionError(''); setMessage('Статус дела обновлён.'); await refetchCase(); }, onError: (err) => { setMessage(''); setActionError(statusErrorMessage(err)); } });
  const editMutation = useMutation({ mutationFn: () => { const { judges_text, participants_text, ...payload } = editForm; return updateCase(caseId, { ...payload, judge_names: lines(judges_text || ''), participants: lines(participants_text || '') }); }, onSuccess: async () => { setActionError(''); setMessage('Дело обновлено'); setIsEditing(false); await refetchCase(); }, onError: (err) => { setMessage(''); setActionError(caseEditErrorMessage(err)); } });
  const deleteMutation = useMutation({ mutationFn: (documentId: string) => deleteCaseDocument(caseId, documentId), onSuccess: async () => { setActionError(''); setMessage('Документ удалён.'); await refetchCase(); }, onError: (err) => { setMessage(''); setActionError(deleteErrorMessage(err)); } });

  const caseInfo = useMemo(() => ({ case_number: c?.case_number, document_number: c?.document_number, court_name: c?.court_name || c?.court, region: c?.region, document_date: c?.document_date, legal_article: c?.legal_article || c?.law_article, judge_names: judges }), [c, judges]);
  const setField = (name: keyof typeof editForm, value: string) => setEditForm((prev) => ({ ...prev, [name]: value }));

  return <AppLayout>
    <ServerState loading={isLoading} error={status === 403 || status === 404 ? null : error} />
    {status === 404 && <p className="error-message">Дело не найдено.</p>}{status === 403 && <p className="error-message">Недостаточно прав для просмотра дела.</p>}
    {!isLoading && !error && c && <>
      <div className="case-actions"><h1>Дело № {val(c.case_number)}</h1>{canManage && <><button className='button button-secondary' type='button' onClick={() => setIsEditing((v) => !v)}>{isEditing ? 'Закрыть редактирование' : 'Редактировать дело'}</button><Link className="button" to={`/staff/cases/${caseId}/upload`}>Загрузить документ</Link></>}</div>
      {message && <p className="success-message">{message}</p>}{actionError && <p className="error-message">{actionError}</p>}
      {currentCaseStatus === 'DRAFT' && <p className="status-warning">Дело находится в черновике и не отображается в публичном поиске.</p>}
      <section className="status-panel"><div><h2>Статус дела</h2><p>Публичный поиск показывает только опубликованные документы.</p></div>{canManage ? <div className="status-controls"><select value={caseStatus} onChange={(event) => setCaseStatus(event.target.value as CaseStatus)}><option value="DRAFT">Черновик</option><option value="PUBLISHED">Опубликовано</option><option value="ARCHIVED">Архивировано</option></select><button type="button" onClick={() => statusMutation.mutate()} disabled={statusMutation.isPending}>Сохранить статус</button></div> : <span className="badge">{val(c.status)}</span>}</section>
      {isEditing && canManage && <section className='case-card'><h2>Редактирование дела</h2><form className='case-edit-form' onSubmit={(e) => { e.preventDefault(); editMutation.mutate(); }}><div className='form-grid'><div><label>ID суда</label><input value={editForm.court_id || ''} onChange={(e) => setField('court_id', e.target.value)} /></div><div><label>Название суда</label><input value={editForm.court_name || ''} onChange={(e) => setField('court_name', e.target.value)} /></div><div><label>Номер дела</label><input required value={editForm.case_number || ''} onChange={(e) => setField('case_number', e.target.value)} /></div><div><label>Номер документа</label><input value={editForm.document_number || ''} onChange={(e) => setField('document_number', e.target.value)} /></div><div><label>Дата документа</label><input type='date' value={editForm.document_date || ''} onChange={(e) => setField('document_date', e.target.value)} /></div><div><label>Инстанция</label><select value={editForm.instance || ''} onChange={(e) => setField('instance', e.target.value)}>{INSTANCE_OPTIONS.map((i) => <option key={i.value} value={i.value}>{i.label}</option>)}</select></div><div><label>Регион</label><select value={editForm.region || ''} onChange={(e) => setField('region', e.target.value)}><option value=''>Выберите регион</option>{RUSSIAN_REGIONS.map((r) => <option key={r} value={r}>{r}</option>)}</select></div><div><label>Статья закона</label><input value={editForm.legal_article || ''} onChange={(e) => setField('legal_article', e.target.value)} /></div><div><label>Судебная практика</label><input value={editForm.judicial_practice || ''} onChange={(e) => setField('judicial_practice', e.target.value)} /></div></div><label>Судьи дела</label><textarea rows={3} value={editForm.judges_text || ''} onChange={(e) => setField('judges_text', e.target.value)} /><label>Участники дела</label><textarea rows={3} value={editForm.participants_text || ''} onChange={(e) => setField('participants_text', e.target.value)} /><div className='form-row'><button className='button' disabled={editMutation.isPending}>Сохранить дело</button><button className='button button-secondary' type='button' onClick={() => setIsEditing(false)}>Отмена</button></div></form></section>}
      <section className="case-card"><h2>Основные сведения</h2><div className="case-meta-grid"><p><b>Номер дела:</b> {val(c.case_number)}</p><p><b>Номер документа:</b> {val(c.document_number)}</p><p><b>Дата документа:</b> {val(c.document_date)}</p><p><b>Суд:</b> {val(c.court_name || c.court)}</p><p><b>Регион:</b> {val(c.region)}</p><p><b>Инстанция:</b> {val(c.instance)}</p><p><b>Статья закона:</b> {val(c.legal_article || c.law_article)}</p><p><b>Судебная практика:</b> {val(c.judicial_practice || c.practice_topic)}</p><p><b>Статус дела:</b> <span className="badge">{val(c.status)}</span></p></div></section>
      <section className="case-card"><h2>Состав суда</h2>{judges.length ? <ul>{judges.map((j: any) => <li key={j}>{j}</li>)}</ul> : <p>Судьи дела не указаны.</p>}</section>
      <section className="case-card"><h2>Участники дела</h2>{participants.length ? <div className="case-meta-grid">{participants.map((p: any, idx: number) => <p key={p.id || idx}><b>{val(p.role)}:</b> {val(p.display_name || p.name || p.username || p)}</p>)}</div> : <p>Участники дела не указаны.</p>}</section>
      <section className="case-card"><h2>Документы дела</h2>{documents.length ? documents.map((d: any) => { const id = docId(d); const documentStatus = statusUpper(d.status); return <article className="document-card" key={id}><div className="document-card-header"><div><h3>{val(d.title)}</h3><p><b>Тип судебного акта:</b> {val(d.act_type || d.document_type)}</p><p><b>Статус:</b> <span className="badge">{val(d.status)}</span></p><p><b>Дата:</b> {val(d.document_date || d.date || c.document_date)}</p></div></div>{['DRAFT', 'ANONYMIZED'].includes(documentStatus) && <p className="status-warning">Документ ещё не опубликован. Публичные пользователи его не увидят.</p>}<div className="case-actions">{id && documentStatus === 'PUBLISHED' && <Link className="button" to={`/documents/${id}`}>Открыть публичную версию</Link>}
{id && documentStatus !== 'PUBLISHED' && <Link className="button button-secondary" to={`/staff/documents/${id}/anonymization`}>Предпросмотр рабочей версии</Link>}{id && canManage && <Link className='button button-secondary' to={`/staff/documents/${id}/anonymization`}>Ручная проверка</Link>}{isAuthenticated && (d.can_view_restored || c.can_view_restored || canManage) && <Link className="button button-secondary" to={`/cases/${caseId}/restored`}>Восстановленные данные</Link>}{canManage && canPublishStatus(d.status) && id && <button type="button" onClick={() => publishMutation.mutate(id)} disabled={publishMutation.isPending}>Опубликовать документ</button>}{canManage && id && <button type='button' className='danger-button' disabled={deleteMutation.isPending} onClick={() => window.confirm('Удалить документ из дела? Это действие будет записано в журнал аудита.') && deleteMutation.mutate(id)}>Удалить документ</button>}{id && documentActionErrors[id] && <div className='publication-error-card'><p className='document-action-error'>{documentActionErrors[id]}</p>{documentActionErrors[id].includes('проверка обезличивания не завершена') && <Link className='button button-secondary' to={`/staff/documents/${id}/anonymization`}>Перейти к ручной проверке</Link>}</div>}
</div><CourtDocumentView title={d.title} text={d.anonymized_text || d.text || d.content || d.public_text || d.full_text} caseInfo={caseInfo} /></article>; }) : <div className="empty-state"><p>Документы пока не загружены.</p>{canManage && <Link className="button" to={`/staff/cases/${caseId}/upload`}>Загрузить документ</Link>}</div>}</section>
    </>}
  </AppLayout>;
}
