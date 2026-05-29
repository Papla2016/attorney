import { useState } from 'react';
import type { RedactionEntity } from '../../api/types';
import { getEntityTypeLabel, PERSON_ROLE_LABELS } from '../../constants/anonymizationLabels';
import { formatMentionFormat } from './helpers';
import MergeEntitiesModal from './MergeEntitiesModal';

type Props = {
  entities: RedactionEntity[];
  selectedIds: string[];
  mergeTarget: string;
  busyId?: string;
  mergeBusy: boolean;
  mergeError?: string;
  onSelect: (id: string, selected: boolean) => void;
  onMergeTargetChange: (id: string) => void;
  onMerge: () => void;
  onClearSelection: () => void;
  onEdit: (entity: RedactionEntity) => void;
  onSplitMention: (entity: RedactionEntity, mentionId: string) => void;
};

export default function EntityRegistryPanel({ entities, selectedIds, mergeTarget, busyId, mergeBusy, mergeError, onSelect, onMergeTargetChange, onMerge, onClearSelection, onEdit, onSplitMention }: Props) {
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  return <section className='anonymization-results-section' aria-label='Обезличенные сущности'>
    <div className='panel-header-row'><h2>Обезличено</h2><span className='badge'>{entities.length}</span></div>
    <MergeEntitiesModal entities={entities} selectedIds={selectedIds} targetId={mergeTarget} busy={mergeBusy} error={mergeError} onTargetChange={onMergeTargetChange} onMerge={onMerge} onClear={onClearSelection} />
    {entities.length === 0 ? <p className='empty-state'>Обезличенных сущностей без проверки пока нет.</p> : <div className='entity-card-list'>
      {entities.map((entity) => {
        const isExpanded = !!expanded[entity.entity_id];
        const role = entity.person_role ? PERSON_ROLE_LABELS[entity.person_role] || entity.person_role : entity.context_label || entity.context_kind || '—';
        return <article className='entity-card' key={entity.entity_id} id={`entity-row-${entity.entity_id}`}>
          <div className='entity-card-main'>
            <label className='entity-checkbox'><input type='checkbox' checked={selectedIds.includes(entity.entity_id)} onChange={(e) => onSelect(entity.entity_id, e.target.checked)} /> Выбрать</label>
            <div><strong className='placeholder-pill'>{entity.placeholder || 'Без обозначения'}</strong><p>{entity.canonical_value}</p></div>
            <div><span className='muted-text'>Тип</span><strong>{getEntityTypeLabel(entity.entity_class)}</strong></div>
            <div><span className='muted-text'>Роль / контекст</span><strong>{role}</strong></div>
            <div><span className='muted-text'>Упоминаний</span><strong>{entity.mentions_count || entity.mentions?.length || 0}</strong></div>
            <div className='mapping-actions'>
              <button type='button' className='button button-secondary' onClick={() => setExpanded((prev) => ({ ...prev, [entity.entity_id]: !isExpanded }))}>{isExpanded ? 'Скрыть варианты' : 'Варианты написания'}</button>
              <button type='button' className='button' onClick={() => onEdit(entity)}>Редактировать</button>
            </div>
          </div>
          {isExpanded && <div className='entity-mentions-block'>
            {(entity.mentions || []).length === 0 ? <p className='empty-state'>Упоминания не переданы API.</p> : <table className='mentions-table'><thead><tr><th>Текст</th><th>Нормализация</th><th>Формат</th><th>Позиция / контекст</th><th>Замена</th><th>Действие</th></tr></thead><tbody>{entity.mentions.map((mention) => <tr key={mention.mention_id} className='mention-row'><td>{mention.surface_value}</td><td>{mention.normalized_value && mention.normalized_value !== mention.surface_value ? mention.normalized_value : '—'}</td><td>{formatMentionFormat(mention.format)}</td><td>{mention.start !== undefined && mention.end !== undefined ? `${mention.start}-${mention.end}` : '—'}</td><td>{mention.replacement_value || entity.placeholder || '—'}</td><td><button type='button' className='button button-secondary' disabled={busyId === mention.mention_id} onClick={() => onSplitMention(entity, mention.mention_id)}>{busyId === mention.mention_id ? 'Отделяем...' : 'Отделить упоминание'}</button></td></tr>)}</tbody></table>}
          </div>}
        </article>;
      })}
    </div>}
  </section>;
}
