import type { PendingReviewEntity } from '../../api/types';
import { getEntityTypeLabel } from '../../constants/anonymizationLabels';
import { mergeCandidateLabel } from './helpers';

type Props = {
  pendingReview: PendingReviewEntity[];
  scanLoading: boolean;
  scanError?: string;
  mergeTargets: Record<string, string>;
  busyId?: string;
  errors: Record<string, string>;
  onMergeTargetChange: (key: string, targetId: string) => void;
  onResolve: (entity: PendingReviewEntity, decision: 'REDACT' | 'KEEP' | 'MERGE_WITH_EXISTING', targetEntityId?: string) => void;
};

export default function PendingReviewPanel({ pendingReview, scanLoading, scanError, mergeTargets, busyId, errors, onMergeTargetChange, onResolve }: Props) {
  return <section className={`pending-review-panel ${pendingReview.length ? 'pending-review-panel-warning' : ''}`} aria-label='Найдено в изменённом тексте'>
    <div className='panel-header-row'>
      <h2>Найдено в изменённом тексте</h2>
      {scanLoading && <span className='scan-loading'>Проверяем добавленный текст...</span>}
    </div>
    {scanError && <p className='error-message'>{scanError}</p>}
    {pendingReview.length === 0 ? <p className='empty-state'>Новых необработанных фрагментов в изменённом тексте нет.</p> : <>
      <p className='publication-blocked-warning'>Публикация недоступна, пока найденные фрагменты не обработаны.</p>
      <div className='pending-card-list'>
        {pendingReview.map((entity, index) => {
          const key = entity.entity_key || `${entity.surface_value}-${index}`;
          const selected = mergeTargets[key] || '';
          return <article className='pending-card' id={`pending-row-${entity.entity_key}`} key={key}>
            <div className='entity-card-main'>
              <div><strong>{entity.surface_value}</strong><p className='muted-text'>{entity.normalized_value || 'Без нормализации'}</p></div>
              <div><span className='muted-text'>Предполагаемый тип</span><strong>{getEntityTypeLabel(entity.entity_class)}</strong></div>
              <div><span className='muted-text'>Причина</span><strong>{entity.reason}</strong></div>
            </div>
            <label>Возможные связи
              <select value={selected} onChange={(e) => onMergeTargetChange(key, e.target.value)} disabled={!entity.merge_candidates?.length}>
                <option value=''>Выберите сущность</option>
                {entity.merge_candidates?.map((candidate) => <option key={candidate.entity_id || candidate.cluster_id} value={candidate.entity_id || ''}>{mergeCandidateLabel(candidate)}</option>)}
              </select>
            </label>
            {errors[key] && <p className='error-message'>{errors[key]}</p>}
            <div className='mapping-actions'>
              <button type='button' className='button' disabled={busyId === key} onClick={() => onResolve(entity, 'REDACT')}>{busyId === key ? 'Обрабатываем...' : 'Обезличить'}</button>
              <button type='button' className='button button-secondary' disabled={busyId === key} onClick={() => onResolve(entity, 'KEEP')}>Оставить в тексте</button>
              <button type='button' className='button button-secondary' disabled={busyId === key || !selected} onClick={() => onResolve(entity, 'MERGE_WITH_EXISTING', selected)}>Связать с существующей записью</button>
            </div>
          </article>;
        })}
      </div>
    </>}
  </section>;
}
