import { useEffect, useMemo, useRef, useState } from 'react';
import { addDocumentMapping, applyRedactionDecision, reanonymizeDocument, saveAnonymization, scanEditedDraft } from '../../api/casesApi';
import type { EntityMapping, PendingMarker, PendingReviewEntity, ReviewMarker } from '../../api/types';
import { ENTITY_TYPE_OPTIONS, getEntityTypeLabel, PERSON_ROLE_LABELS } from '../../constants/anonymizationLabels';
import RichDocumentEditor from '../documents/RichDocumentEditor';
import CourtDocumentView from '../documents/CourtDocumentView';
import { plainTextToTiptapDocument } from '../../utils/tiptapDocument';

type Props = { documentId: string; caseId?: string; initialData?: any; onSaved?: () => void; sourceContent?: unknown; sourceText?: string };
const mappingsFrom = (data: any): EntityMapping[] => data?.mappings || data?.entity_mappings || data?.anonymization?.mappings || [];
const keptFrom = (data: any): EntityMapping[] => data?.recognized_but_kept || data?.anonymization?.recognized_but_kept || [];
const reviewFrom = (data: any): EntityMapping[] => data?.review_entities || data?.anonymization?.review_entities || [];
const markersFrom = (data: any): ReviewMarker[] => data?.review_markers || data?.anonymization?.review_markers || [];
const pendingFrom = (data: any): PendingReviewEntity[] => data?.pending_review || [];
const pendingMarkersFrom = (data: any): PendingMarker[] => data?.pending_markers || [];
const textFrom = (data: any) => data?.anonymized_text || data?.anonymization?.anonymized_text || data?.anonymized_plain_text || '';
const contentFrom = (data: any) => data?.anonymized_content || null;

export default function AnonymizationWorkspace({ documentId, initialData, sourceText }: Props) {
  const [mappings, setMappings] = useState<EntityMapping[]>(mappingsFrom(initialData));
  const [recognizedButKept, setRecognizedButKept] = useState<EntityMapping[]>(keptFrom(initialData));
  const [reviewEntities, setReviewEntities] = useState<EntityMapping[]>(reviewFrom(initialData));
  const [reviewMarkers, setReviewMarkers] = useState<ReviewMarker[]>(markersFrom(initialData));
  const [pendingReview, setPendingReview] = useState<PendingReviewEntity[]>(pendingFrom(initialData));
  const [pendingMarkers, setPendingMarkers] = useState<PendingMarker[]>(pendingMarkersFrom(initialData));
  const [contentRevision, setContentRevision] = useState(0);
  const [draftRevision, setDraftRevision] = useState(0);
  const [isApplyingServerContent, setIsApplyingServerContent] = useState(false);
  const [scanLoading, setScanLoading] = useState(false);
  const [scanError, setScanError] = useState('');
  const [tab, setTab] = useState<'REDACT'|'KEEP'|'REVIEW'>('REDACT');
  const [resultTab, setResultTab] = useState<'EDIT'|'PREVIEW'>('EDIT');
  const [anonymizedText, setAnonymizedText] = useState(textFrom(initialData));
  const [anonymizedContent, setAnonymizedContent] = useState<any>(contentFrom(initialData));
  const [documentChangedManually, setDocumentChangedManually] = useState(false);
  const [mergeTargets, setMergeTargets] = useState<Record<string, string>>({});
  const [warning, setWarning] = useState(''); const [error, setError] = useState(''); const [message, setMessage] = useState('');
  const [selectedText, setSelectedText] = useState(''); const [entityType, setEntityType] = useState('PERSON_FULL_NAME');
  const pendingPanelRef = useRef<HTMLDivElement | null>(null);

  const applyResponse = (data: any) => {
    setIsApplyingServerContent(true);
    setMappings(mappingsFrom(data)); setRecognizedButKept(keptFrom(data)); setReviewEntities(reviewFrom(data)); setReviewMarkers(markersFrom(data));
    setPendingReview(pendingFrom(data)); setPendingMarkers(pendingMarkersFrom(data));
    setAnonymizedText(textFrom(data)); setAnonymizedContent(contentFrom(data));
    setContentRevision((v) => v + 1);
    if (!data?.anonymized_content) setWarning('Сервер не вернул форматированную версию документа. Проверьте поддержку сохранения форматирования на backend.');
    setTimeout(() => setIsApplyingServerContent(false), 0);
  };

  useEffect(() => {
    if (!documentChangedManually || isApplyingServerContent || !anonymizedText.trim()) return;
    const revision = draftRevision;
    const t = setTimeout(async () => {
      try {
        setScanLoading(true); setScanError('');
        const res = await scanEditedDraft(documentId, { text: anonymizedText, content: anonymizedContent, content_format: 'TIPTAP_JSON', document_revision: revision });
        const data = res.data;
        if (data?.document_revision !== undefined && data.document_revision !== draftRevision) return;
        setPendingReview(pendingFrom(data));
        setPendingMarkers(pendingMarkersFrom(data));
      } catch {
        setScanError('Не удалось проверить добавленный текст.');
      } finally { setScanLoading(false); }
    }, 800);
    return () => clearTimeout(t);
  }, [draftRevision]);

  const groupedKept = useMemo(() => { const map = new Map<string, EntityMapping[]>(); recognizedButKept.forEach((item) => { const key = item.cluster_id || `${item.entity_class || item.entity_type}:${item.normalized_value || item.original_value}`; map.set(key, [...(map.get(key) || []), item]); }); return [...map.values()]; }, [recognizedButKept]);

  return <div className='anonymization-workspace'>
    <h2>Результат обезличивания</h2>
    {warning && <p className='warning-message'>{warning}</p>}{error && <p className='error-message'>{error}</p>}{message && <p className='success-message'>{message}</p>}
    {pendingReview.length > 0 && <div className='publication-blocked-warning'>Документ содержит необработанные фрагменты. Сначала обработайте найденные персональные данные.</div>}
    <div className='anonymized-editor-tabs'><button className='button button-secondary' onClick={()=>setResultTab('EDIT')}>Редактирование обезличенного текста</button><button className='button button-secondary' onClick={()=>setResultTab('PREVIEW')}>Предпросмотр обезличенного документа</button></div>
    {resultTab==='EDIT' ? <RichDocumentEditor value={anonymizedContent || plainTextToTiptapDocument(anonymizedText)} contentRevision={contentRevision} editable onChange={({ json, text }) => { setAnonymizedContent(json); setAnonymizedText(text); setDocumentChangedManually(true); if (!isApplyingServerContent) setDraftRevision((v) => v + 1); }} onSelectionChange={setSelectedText} reviewMarkers={reviewMarkers} pendingMarkers={pendingMarkers} onReviewMarkerClick={() => setTab('REVIEW')} onPendingMarkerClick={(entityKey) => { setTimeout(() => pendingPanelRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 0); const el = document.getElementById(`pending-row-${entityKey}`); el?.classList.add('pending-review-row-active'); setTimeout(() => el?.classList.remove('pending-review-row-active'), 1200); }} /> : <><div><strong>Рабочая обезличенная версия документа</strong>{pendingReview.length > 0 && <p className='publication-blocked-warning'>Публикация недоступна: есть фрагменты, требующие обработки</p>}{reviewMarkers.length > 0 && <p className='warning-message'>Есть обезличенные значения, требующие подтверждения</p>}</div><CourtDocumentView variant='anonymizedPreview' title='Черновик обезличенного документа' content={anonymizedContent || plainTextToTiptapDocument(anonymizedText)} contentFormat='TIPTAP_JSON' text={anonymizedText} /></>}

    <div ref={pendingPanelRef} className='pending-review-panel'><h3>Найдено в изменённом тексте</h3>{scanLoading && <p className='scan-loading'>Проверяем добавленный текст...</p>}{scanError && <p className='error-message'>{scanError}</p>}{!scanLoading && pendingReview.length===0 && <p>Новых фрагментов, требующих обработки, не найдено.</p>}{pendingReview.length>0 && <table className='mapping-table'><thead><tr><th>Фрагмент</th><th>Предполагаемый тип</th><th>Причина</th><th>Возможные связи</th><th>Действия</th></tr></thead><tbody>{pendingReview.map((p,i)=>{const key=p.entity_key || String(i); const selected=mergeTargets[key] || (p.merge_candidates?.length===1 ? p.merge_candidates[0].cluster_id : ''); return <tr id={`pending-row-${p.entity_key}`} key={key} className='pending-review-row'><td>{p.surface_value}</td><td>{getEntityTypeLabel(p.entity_class)}</td><td>{p.reason}</td><td>{p.merge_candidates?.length ? <select value={selected} onChange={(e)=>setMergeTargets((prev)=>({...prev,[key]:e.target.value}))}><option value=''>Выберите сущность</option>{p.merge_candidates?.map((m)=><option key={m.cluster_id} value={m.cluster_id}>{m.placeholder || m.cluster_id} — {m.normalized_value}</option>)}</select> : 'Нет кандидатов'}</td><td><button className='button' onClick={async()=>{const r=await applyRedactionDecision(documentId,{entity_key:p.entity_key,selected_text:p.surface_value,decision:'REDACT',entity_class:p.entity_class,reason:'Обезличено после проверки дописанного текста'});applyResponse(r.data);}}>Обезличить</button> <button className='button button-secondary' onClick={async()=>{const r=await applyRedactionDecision(documentId,{entity_key:p.entity_key,selected_text:p.surface_value,decision:'KEEP',entity_class:p.entity_class,reason:'Оставлено пользователем'});applyResponse(r.data);}}>Оставить в тексте</button> {p.merge_candidates?.length ? <button className='button button-secondary' disabled={!selected} onClick={async()=>{if(!selected) return; const r=await applyRedactionDecision(documentId,{entity_key:p.entity_key,selected_text:p.surface_value,decision:'MERGE_WITH_EXISTING',entity_class:p.entity_class,target_cluster_id:selected,reason:'Связано пользователем с существующей сущностью'});applyResponse(r.data);}}>Связать с существующей записью</button> : null}</td></tr>;})}</tbody></table>}</div>
    <button className='button button-secondary' onClick={async()=>{ const r = await reanonymizeDocument(documentId, { mappings, publication_redaction_mode: 'NORMATIVE' }); applyResponse(r.data); }}>Повторно обезличить</button>
    <button className='button' onClick={async()=>{const r=await saveAnonymization(documentId,{anonymized_text:anonymizedText,anonymized_content:anonymizedContent,content_format:'TIPTAP_JSON',mappings}); applyResponse(r.data); setDocumentChangedManually(false); setMessage(pendingReview.length ? 'Документ сохранён как рабочая версия. Для публикации необходимо обработать найденные фрагменты.' : 'Изменения обезличенного документа сохранены.');}}>Сохранить документ</button>
    {sourceText && <p className='warning-message'>Исходный текст изменён. Таблица соответствия может быть неактуальна. Выполните обезличивание повторно.</p>}
  </div>;
}
