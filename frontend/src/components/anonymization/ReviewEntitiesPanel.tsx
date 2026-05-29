import type { RedactionEntity } from '../../api/types';
import { getEntityTypeLabel } from '../../constants/anonymizationLabels';
import { mergeCandidateLabel, selectedTextForEntity } from './helpers';

type Props = {
  reviewEntities: RedactionEntity[];
  mergeTargets: Record<string, string>;
  busyId?: string;
  actionsDisabled?: boolean;
  errors: Record<string, string>;
  onMergeTargetChange: (key: string, targetId: string) => void;
  onResolve: (entity: RedactionEntity, decision: 'REDACT' | 'KEEP' | 'MERGE_WITH_EXISTING', targetEntityId?: string) => void;
};

export default function ReviewEntitiesPanel({ reviewEntities, mergeTargets, busyId, actionsDisabled = false, errors, onMergeTargetChange, onResolve }: Props) {
  return <section className='anonymization-results-section review-panel' aria-label='Сущности, требующие проверки'>
    <div className='panel-header-row'><h2>Требует проверки</h2><span className='badge badge-warning'>{reviewEntities.length}</span></div>
    {reviewEntities.length === 0 ? <p className='empty-state'>Нет обезличенных сущностей, ожидающих решения пользователя.</p> : <div className='review-card-list'>
      {reviewEntities.map((entity) => {
        const key = entity.entity_key || entity.entity_id;
        const selectedText = selectedTextForEntity(entity);
        const selected = mergeTargets[key] || '';
        return <article className='review-card' key={key} id={`review-row-${key}`}>
          <div className='entity-card-main'>
            <div><strong className='placeholder-pill'>{entity.placeholder || 'Проверка'}</strong><p>{selectedText || '—'}</p></div>
            <div><span className='muted-text'>Тип</span><strong>{getEntityTypeLabel(entity.entity_class)}</strong></div>
            <div><span className='muted-text'>Причина</span><strong>{entity.review_reason || 'Нужно решение пользователя'}</strong></div>
          </div>
          <div className='review-actions-grid'>
            {!!entity.merge_candidates?.length && <label>Связать с существующей записью
              <select value={selected} onChange={(e) => onMergeTargetChange(key, e.target.value)}>
                <option value=''>Выберите запись</option>
                {entity.merge_candidates.map((candidate) => <option key={candidate.entity_id || candidate.cluster_id} value={candidate.entity_id || ''}>{mergeCandidateLabel(candidate)}</option>)}
              </select>
            </label>}
            {errors[key] && <p className='error-message'>{errors[key]}</p>}
            <div className='mapping-actions'>
              <button type='button' className='button' disabled={actionsDisabled || busyId === key} onClick={() => onResolve(entity, 'REDACT')}>{busyId === key ? 'Обрабатываем...' : 'Подтвердить обезличивание'}</button>
              <button type='button' className='button button-secondary' disabled={actionsDisabled || busyId === key} onClick={() => onResolve(entity, 'KEEP')}>Оставить в тексте</button>
              <button type='button' className='button button-secondary' disabled={actionsDisabled || busyId === key || !selected} onClick={() => onResolve(entity, 'MERGE_WITH_EXISTING', selected)}>Связать с существующей записью</button>
            </div>
          </div>
        </article>;
      })}
    </div>}
  </section>;
}
