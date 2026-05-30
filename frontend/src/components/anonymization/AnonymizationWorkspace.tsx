import { useEffect, useMemo, useRef, useState } from 'react';
import { applyRedactionDecision, getDocumentAnonymization, mergeDocumentEntities, publishDocument, reanonymizeDocument, repairPlaceholders, saveAnonymization, scanEditedDraft, splitEntityMention, updateDocumentEntity } from '../../api/casesApi';
import type { AnonymizationResult, EntityMapping, PendingMarker, PendingReviewEntity, RedactionEntity, ReviewMarker } from '../../api/types';
import { plainTextToTiptapDocument } from '../../utils/tiptapDocument';
import AnonymizedDocumentPanel from './AnonymizedDocumentPanel';
import EntityEditorModal from './EntityEditorModal';
import EntityRegistryPanel from './EntityRegistryPanel';
import KeptEntitiesPanel from './KeptEntitiesPanel';
import PendingReviewPanel from './PendingReviewPanel';
import ReviewEntitiesPanel from './ReviewEntitiesPanel';
import { getApiErrorMessage, getEntityKey, legacyMappingToEntity, selectedTextForEntity } from './helpers';

type Props = { documentId: string; caseId?: string; initialData?: AnonymizationResult; onSaved?: () => void; sourceContent?: unknown; sourceText?: string };
type ActionName = 'save' | 'reanonymize' | 'publish' | 'repair' | 'merge' | 'edit' | 'split' | 'decision' | '';

const pick = <T,>(obj: Partial<AnonymizationResult> | undefined, key: keyof AnonymizationResult, fallback: T): T => (key in (obj || {}) ? ((obj as any)[key] ?? fallback) : fallback);
const hasOwn = (obj: unknown, key: string) => Object.prototype.hasOwnProperty.call(obj || {}, key);

export default function AnonymizationWorkspace({ documentId, initialData, onSaved, sourceText }: Props) {
  const [mappings, setMappings] = useState<EntityMapping[]>(initialData?.mappings || []);
  const [entities, setEntities] = useState<RedactionEntity[]>(initialData?.entities || (initialData?.mappings || []).map((m, i) => legacyMappingToEntity(m, i, 'REDACT')));
  const [keptEntities, setKeptEntities] = useState<RedactionEntity[]>(initialData?.kept_entities || (initialData?.recognized_but_kept || []).map((m, i) => legacyMappingToEntity(m, i, 'KEEP')));
  const [reviewEntities, setReviewEntities] = useState<RedactionEntity[]>(initialData?.review_entities || []);
  const [reviewMarkers, setReviewMarkers] = useState<ReviewMarker[]>(initialData?.review_markers || []);
  const [pendingReview, setPendingReview] = useState<PendingReviewEntity[]>(initialData?.pending_review || []);
  const [pendingMarkers, setPendingMarkers] = useState<PendingMarker[]>(initialData?.pending_markers || []);
  const [anonymizedText, setAnonymizedText] = useState(initialData?.anonymized_text || '');
  const [anonymizedContent, setAnonymizedContent] = useState<unknown>(initialData?.anonymized_content || plainTextToTiptapDocument(initialData?.anonymized_text || ''));
  const [resultTab, setResultTab] = useState<'EDIT' | 'PREVIEW'>('EDIT');
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [mergeTarget, setMergeTarget] = useState('');
  const [mergeTargets, setMergeTargets] = useState<Record<string, string>>({});
  const [editingEntity, setEditingEntity] = useState<RedactionEntity | null>(null);
  const [activeAction, setActiveAction] = useState<ActionName>('');
  const [busyEntityId, setBusyEntityId] = useState('');
  const [warning, setWarning] = useState('');
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [rowErrors, setRowErrors] = useState<Record<string, string>>({});
  const [mergeError, setMergeError] = useState('');
  const [editorError, setEditorError] = useState('');
  const [contentRevision, setContentRevision] = useState(0);
  const [draftRevision, setDraftRevision] = useState(0);
  const [documentChangedManually, setDocumentChangedManually] = useState(false);
  const [isApplyingServerContent, setIsApplyingServerContent] = useState(false);
	const lastScannedDraftRevisionRef = useRef<number | null>(null);
	const scanInFlightDraftRevisionRef = useRef<number | null>(null);
  const [scanLoading, setScanLoading] = useState(false);
  const [scanError, setScanError] = useState('');
  const pendingPanelRef = useRef<HTMLDivElement | null>(null);

  const applyResponse = (data: Partial<AnonymizationResult>, mode: 'FULL' | 'PENDING_ONLY' = 'FULL') => {
    setIsApplyingServerContent(true);
    if (hasOwn(data, 'pending_review')) setPendingReview(pick(data, 'pending_review', []));
    if (hasOwn(data, 'pending_markers')) setPendingMarkers(pick(data, 'pending_markers', []));
    if (mode === 'FULL') {
      if (hasOwn(data, 'mappings')) setMappings(pick(data, 'mappings', []));
      if (hasOwn(data, 'entities')) setEntities(pick(data, 'entities', []));
      else if (hasOwn(data, 'mappings')) setEntities(pick(data, 'mappings', []).map((m, i) => legacyMappingToEntity(m, i, 'REDACT')));
      if (hasOwn(data, 'kept_entities')) setKeptEntities(pick(data, 'kept_entities', []));
      else if (hasOwn(data, 'recognized_but_kept')) setKeptEntities(pick(data, 'recognized_but_kept', []).map((m, i) => legacyMappingToEntity(m, i, 'KEEP')));
      if (hasOwn(data, 'review_entities')) setReviewEntities(pick(data, 'review_entities', []));
      if (hasOwn(data, 'review_markers')) setReviewMarkers(pick(data, 'review_markers', []));
      if (hasOwn(data, 'anonymized_text')) setAnonymizedText(pick(data, 'anonymized_text', ''));
      if (hasOwn(data, 'anonymized_content')) setAnonymizedContent(pick(data, 'anonymized_content', null));
      setContentRevision((v) => v + 1);
    }
    setTimeout(() => setIsApplyingServerContent(false), 0);
  };

  const syncFull = async () => applyResponse((await getDocumentAnonymization(documentId)).data, 'FULL');
  const provider = initialData?.ner_provider;

	useEffect(() => {
		if (!documentChangedManually || isApplyingServerContent || !anonymizedText.trim()) return;

		if (
			lastScannedDraftRevisionRef.current === draftRevision ||
			scanInFlightDraftRevisionRef.current === draftRevision
		) {
			return;
		}

		const revision = draftRevision;

		const timer = setTimeout(async () => {
			if (
				lastScannedDraftRevisionRef.current === revision ||
				scanInFlightDraftRevisionRef.current === revision
			) {
				return;
			}

			scanInFlightDraftRevisionRef.current = revision;

			try {
				setScanLoading(true);
				setScanError('');

				const res = await scanEditedDraft(documentId, {
					text: anonymizedText,
					content: anonymizedContent,
					content_format: 'TIPTAP_JSON',
					document_revision: revision,
				});

				applyResponse(res.data, 'PENDING_ONLY');
				lastScannedDraftRevisionRef.current = revision;
			} catch (err) {
				setScanError(getApiErrorMessage(err));
				lastScannedDraftRevisionRef.current = revision;
			} finally {
				scanInFlightDraftRevisionRef.current = null;
				setScanLoading(false);
			}
		}, 800);

		return () => clearTimeout(timer);
	}, [anonymizedContent, anonymizedText, documentChangedManually, documentId, draftRevision, isApplyingServerContent]);

  const redactedEntities = useMemo(() => entities.filter((entity) => entity.redaction_decision === 'REDACT' && !entity.requires_review), [entities]);
  const statusCounts = { redacted: redactedEntities.length, review: reviewEntities.length, kept: keptEntities.length, pending: pendingReview.length };
  const publicationBlocked = statusCounts.review > 0 || statusCounts.pending > 0;
  const hasUnvalidatedDraft = documentChangedManually || scanLoading;
  const publishBlockedByState = publicationBlocked || hasUnvalidatedDraft;
  const serverMutationInFlight = !!activeAction || !!busyEntityId;
  const actionsDisabled = hasUnvalidatedDraft || serverMutationInFlight;
  const blockIfUnvalidatedDraft = () => {
    if (!hasUnvalidatedDraft) return false;
    setWarning('Сначала сохраните изменения и дождитесь проверки добавленного текста.');
    return true;
  };

  const runAction = async (action: ActionName, fn: () => Promise<void>, success?: string) => {
    setActiveAction(action);
    setError('');
    setWarning('');
    setMessage('');
    try {
      await fn();
      if (success) setMessage(success);
    } catch (err) {
      setError(getApiErrorMessage(err));
    } finally {
      setActiveAction('');
    }
  };

  const handleSave = () => runAction('save', async () => {
    setScanLoading(true);
    try {
      const scan = await scanEditedDraft(documentId, { text: anonymizedText, content: anonymizedContent, content_format: 'TIPTAP_JSON', document_revision: draftRevision });
			lastScannedDraftRevisionRef.current = draftRevision;
      applyResponse(scan.data, 'PENDING_ONLY');
      const res = await saveAnonymization(documentId, { anonymized_text: anonymizedText, anonymized_content: anonymizedContent, content_format: 'TIPTAP_JSON', mappings });
      applyResponse(res.data, 'FULL');
      setDocumentChangedManually(false);
      const scanPending = scan.data.pending_review || [];
      setMessage(scanPending.length ? 'Документ сохранён как рабочая версия. Для публикации необходимо обработать найденные фрагменты.' : 'Изменения обезличенного документа сохранены.');
      onSaved?.();
    } finally {
      setScanLoading(false);
    }
  });

  const handleReanonymize = () => {
    if (hasUnvalidatedDraft) {
      setWarning('Сначала сохраните изменения и дождитесь проверки добавленного текста.');
      return;
    }
    return runAction('reanonymize', async () => {
      const res = await reanonymizeDocument(documentId, { mappings, publication_redaction_mode: 'NORMATIVE' });
      applyResponse(res.data, 'FULL');
    }, 'Документ повторно обезличен.');
  };

  const handlePublish = () => {
    if (hasUnvalidatedDraft) {
      setWarning('Сначала сохраните изменения и дождитесь проверки добавленного текста.');
      return;
    }
    if (publicationBlocked) {
      setWarning('Публикация недоступна, пока не обработаны все найденные фрагменты.');
      return;
    }
    return runAction('publish', async () => {
      await publishDocument(documentId);
      onSaved?.();
    }, 'Документ опубликован.');
  };

  const handleRepair = () => {
    if (blockIfUnvalidatedDraft()) return;
    return runAction('repair', async () => {
      const res = await repairPlaceholders(documentId);
      applyResponse(res.data, 'FULL');
    }, 'Условные обозначения проверены и восстановлены.');
  };

  const handleEntitySelection = (id: string, selected: boolean) => {
    setMergeError('');
    setSelectedIds((prev) => selected ? [...new Set([...prev, id])] : prev.filter((item) => item !== id));
    if (!selected && mergeTarget === id) setMergeTarget('');
  };

  const handleMerge = () => {
    if (blockIfUnvalidatedDraft()) return;
    const selected = redactedEntities.filter((entity) => selectedIds.includes(entity.entity_id));
    if (selected.length < 2 || !mergeTarget) return;
    const classes = new Set(selected.map((entity) => entity.entity_class));
    if (classes.size > 1) {
      setMergeError('Можно объединять только сущности одного типа данных.');
      return;
    }
    return runAction('merge', async () => {
      const res = await mergeDocumentEntities(documentId, { target_entity_id: mergeTarget, source_entity_ids: selectedIds.filter((id) => id !== mergeTarget) });
      applyResponse(res.data, 'FULL');
      setSelectedIds([]);
      setMergeTarget('');
      setMergeError('');
    }, 'Записи объединены.');
  };

  const handleEditSave = async (payload: { canonical_value: string; entity_class: string; person_role?: string; context_label?: string }) => {
    if (!editingEntity) return;
    if (blockIfUnvalidatedDraft()) return;
    setActiveAction('edit');
    setEditorError('');
    try {
      const res = await updateDocumentEntity(documentId, editingEntity.entity_id, payload);
      applyResponse(res.data, 'FULL');
      setEditingEntity(null);
      setMessage('Сущность обновлена.');
    } catch (err) {
      setEditorError(getApiErrorMessage(err));
    } finally {
      setActiveAction('');
    }
  };

  const handleSplitMention = async (entity: RedactionEntity, mentionId: string) => {
    if (blockIfUnvalidatedDraft()) return;
    setBusyEntityId(mentionId);
    setError('');
    try {
      const res = await splitEntityMention(documentId, entity.entity_id, mentionId);
      applyResponse(res.data, 'FULL');
      setMessage('Упоминание отделено в новую сущность.');
    } catch (err) {
      setError(getApiErrorMessage(err));
    } finally {
      setBusyEntityId('');
    }
  };

  const resolveReviewEntity = async (entity: RedactionEntity, decision: 'REDACT' | 'KEEP' | 'MERGE_WITH_EXISTING', targetEntityId?: string) => {
    if (blockIfUnvalidatedDraft()) return;
    const key = getEntityKey(entity);
    const selectedText = selectedTextForEntity(entity);
    setRowErrors((prev) => ({ ...prev, [key]: '' }));
    if (!selectedText) {
      setRowErrors((prev) => ({ ...prev, [key]: 'Не удалось определить значение для проверки.' }));
      return;
    }
    setBusyEntityId(key);
    try {
      const res = await applyRedactionDecision(documentId, { entity_key: key, selected_text: selectedText, entity_class: entity.entity_class, decision, target_entity_id: targetEntityId, reason: decision === 'KEEP' ? 'Оставлено пользователем после проверки' : 'Подтверждено пользователем после проверки' });
      applyResponse(res.data, 'FULL');
      setMessage('Решение применено.');
    } catch (err) {
      setRowErrors((prev) => ({ ...prev, [key]: getApiErrorMessage(err) }));
    } finally {
      setBusyEntityId('');
    }
  };

  const resolvePendingEntity = async (entity: PendingReviewEntity, decision: 'REDACT' | 'KEEP' | 'MERGE_WITH_EXISTING', targetEntityId?: string) => {
    if (blockIfUnvalidatedDraft()) return;
    const key = entity.entity_key || entity.surface_value;
    setRowErrors((prev) => ({ ...prev, [key]: '' }));
    if (!entity.surface_value) {
      setRowErrors((prev) => ({ ...prev, [key]: 'Не удалось определить значение для проверки.' }));
      return;
    }
    setBusyEntityId(key);
    try {
      const res = await applyRedactionDecision(documentId, { entity_key: entity.entity_key, selected_text: entity.surface_value, entity_class: entity.entity_class, decision, target_entity_id: targetEntityId, reason: decision === 'REDACT' ? 'Обезличено после проверки дописанного текста' : decision === 'KEEP' ? 'Оставлено пользователем' : 'Связано пользователем с существующей сущностью' });
      applyResponse(res.data, 'FULL');
      setMessage('Решение применено.');
    } catch (err) {
      setRowErrors((prev) => ({ ...prev, [key]: getApiErrorMessage(err) }));
    } finally {
      setBusyEntityId('');
    }
  };

  const redactKeptEntity = async (entity: RedactionEntity) => {
    if (blockIfUnvalidatedDraft()) return;
    const key = getEntityKey(entity);
    const selectedText = selectedTextForEntity(entity);
    setRowErrors((prev) => ({ ...prev, [key]: '' }));
    if (!selectedText) {
      setRowErrors((prev) => ({ ...prev, [key]: 'Не удалось определить значение для обезличивания.' }));
      return;
    }
    setBusyEntityId(key);
    try {
      const res = await applyRedactionDecision(documentId, { entity_key: key, selected_text: selectedText, entity_class: entity.entity_class, decision: 'REDACT', reason: 'Обезличено пользователем из списка оставленных значений' });
      applyResponse(res.data, 'FULL');
      setMessage('Сущность обезличена.');
    } catch (err) {
      setRowErrors((prev) => ({ ...prev, [key]: getApiErrorMessage(err) }));
    } finally {
      setBusyEntityId('');
    }
  };

  const scrollToEntity = (entityId: string) => {
    document.getElementById(`entity-row-${entityId}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  };
  const scrollToPending = (entityKey: string) => {
    const row = entityKey ? document.getElementById(`pending-row-${entityKey}`) : null;
    (row || pendingPanelRef.current)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  };

  return <div className='anonymization-workspace'>
    <section className='workspace-status-panel'>
      <div className='panel-header-row'>
        <div><h1>Обезличивание документа</h1><p className='muted-text'>{provider ? 'Используется Natasha и правила' : 'Используются только правила'}</p></div>
        <div className='document-actions'>
          <button type='button' className='button button-secondary' disabled={serverMutationInFlight} onClick={handleSave}>{activeAction === 'save' ? 'Сохраняем...' : 'Сохранить изменения'}</button>
          <button type='button' className='button button-secondary' disabled={actionsDisabled} onClick={handleReanonymize}>{activeAction === 'reanonymize' ? 'Обезличиваем...' : 'Повторно обезличить'}</button>
          <button type='button' className='button' disabled={serverMutationInFlight || publishBlockedByState} onClick={handlePublish}>{activeAction === 'publish' ? 'Публикуем...' : 'Опубликовать'}</button>
        </div>
      </div>
      <div className='workspace-counters'>
        <span className='counter-card'>Обезличено <strong>{statusCounts.redacted}</strong></span>
        <span className='counter-card warning-counter'>Требует проверки <strong>{statusCounts.review}</strong></span>
        <span className='counter-card'>Оставлено в тексте <strong>{statusCounts.kept}</strong></span>
        <span className='counter-card warning-counter'>Найдено в изменениях <strong>{statusCounts.pending}</strong></span>
      </div>
      {publishBlockedByState && <p className='publication-blocked-warning'>{hasUnvalidatedDraft ? 'Сначала сохраните изменения и дождитесь проверки добавленного текста.' : 'Публикация недоступна, пока не обработаны все найденные фрагменты.'}</p>}
      {warning && <p className='warning-message'>{warning}</p>}
      {error && <p className='error-message'>{error}</p>}
      {message && <p className='success-message'>{message}</p>}
    </section>

    <AnonymizedDocumentPanel
      mode={resultTab}
      onModeChange={setResultTab}
      anonymizedText={anonymizedText}
      anonymizedContent={anonymizedContent}
      contentRevision={contentRevision}
      reviewMarkers={reviewMarkers}
      pendingMarkers={pendingMarkers}
      redactionMarkers={redactedEntities}
      onChange={({ json, text }) => { setAnonymizedContent(json); setAnonymizedText(text); setDocumentChangedManually(true); setDraftRevision((v) => v + 1); }}
      onRedactionClick={scrollToEntity}
      onPendingClick={(key) => scrollToPending(key)}
      onReviewClick={() => document.querySelector('.review-panel')?.scrollIntoView({ behavior: 'smooth', block: 'center' })}
      editorLocked={serverMutationInFlight}
    />

    <div className='document-actions'>
      <button type='button' className='button button-secondary' disabled={actionsDisabled} onClick={handleRepair}>{activeAction === 'repair' ? 'Проверяем...' : 'Восстановить placeholder marks'}</button>
      {sourceText && <p className='warning-message'>Исходный текст изменён. Таблица соответствия может быть неактуальна. Выполните обезличивание повторно.</p>}
    </div>

    <div className='workspace-panels-grid'>
      {hasUnvalidatedDraft && <p className='manual-decision-warning'>Сохраните изменения документа, чтобы продолжить работу с сущностями.</p>}
      <EntityRegistryPanel entities={redactedEntities} selectedIds={selectedIds} mergeTarget={mergeTarget} busyId={busyEntityId} mergeBusy={activeAction === 'merge'} mergeError={mergeError} onSelect={handleEntitySelection} onMergeTargetChange={setMergeTarget} onMerge={handleMerge} onClearSelection={() => { setSelectedIds([]); setMergeTarget(''); setMergeError(''); }} onEdit={setEditingEntity} onSplitMention={handleSplitMention} actionsDisabled={actionsDisabled} />
      <div ref={pendingPanelRef}><PendingReviewPanel pendingReview={pendingReview} scanLoading={scanLoading} scanError={scanError} mergeTargets={mergeTargets} busyId={busyEntityId} errors={rowErrors} onMergeTargetChange={(key, targetId) => setMergeTargets((prev) => ({ ...prev, [key]: targetId }))} onResolve={resolvePendingEntity} actionsDisabled={actionsDisabled} /></div>
      <ReviewEntitiesPanel reviewEntities={reviewEntities} mergeTargets={mergeTargets} busyId={busyEntityId} errors={rowErrors} onMergeTargetChange={(key, targetId) => setMergeTargets((prev) => ({ ...prev, [key]: targetId }))} onResolve={resolveReviewEntity} actionsDisabled={actionsDisabled} />
      <KeptEntitiesPanel keptEntities={keptEntities} busyId={busyEntityId} errors={rowErrors} onRedact={redactKeptEntity} actionsDisabled={actionsDisabled} />
    </div>

    <EntityEditorModal entity={editingEntity} busy={activeAction === 'edit'} error={editorError} onClose={() => setEditingEntity(null)} onSave={handleEditSave} actionsDisabled={actionsDisabled} />
  </div>;
}
