import { useState } from 'react';
import type { RedactionEntity } from '../../api/types';
import { getEntityTypeLabel, PERSON_ROLE_LABELS } from '../../constants/anonymizationLabels';

type Props = { keptEntities: RedactionEntity[]; busyId?: string; actionsDisabled?: boolean; errors: Record<string, string>; onRedact: (entity: RedactionEntity) => void };

export default function KeptEntitiesPanel({ keptEntities, busyId, actionsDisabled = false, errors, onRedact }: Props) {
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  return <section className='anonymization-results-section kept-panel' aria-label='Оставленные в тексте сущности'>
    <div className='panel-header-row'><h2>Оставлено в тексте</h2><span className='badge'>{keptEntities.length}</span></div>
    {keptEntities.length === 0 ? <p className='empty-state'>Нет сущностей, оставленных в тексте.</p> : <div className='entity-card-list'>
      {keptEntities.map((entity) => {
        const key = entity.entity_key || entity.entity_id;
        const role = entity.person_role ? PERSON_ROLE_LABELS[entity.person_role] || entity.person_role : entity.context_label || entity.context_kind || '—';
        return <article className='entity-card kept-row' key={key}>
          <div className='entity-card-main'>
            <div><strong>{entity.canonical_value || entity.normalized_value || 'Без значения'}</strong><p className='muted-text'>{entity.placeholder || 'Без условного обозначения'}</p></div>
            <div><span className='muted-text'>Тип</span><strong>{getEntityTypeLabel(entity.entity_class)}</strong></div>
            <div><span className='muted-text'>Роль / контекст</span><strong>{role}</strong></div>
            <div><span className='muted-text'>Упоминаний</span><strong>{entity.mentions_count || entity.mentions?.length || 0}</strong></div>
            <div className='mapping-actions'><button type='button' className='button button-secondary' onClick={() => setExpanded((prev) => ({ ...prev, [key]: !prev[key] }))}>{expanded[key] ? 'Скрыть варианты' : 'Варианты написания'}</button><button type='button' className='button' disabled={actionsDisabled || busyId === key} onClick={() => onRedact(entity)}>{busyId === key ? 'Обезличиваем...' : 'Обезличить'}</button></div>
          </div>
          {errors[key] && <p className='error-message'>{errors[key]}</p>}
          {expanded[key] && <ul className='mentions-list'>{(entity.mentions || []).map((mention) => <li key={mention.mention_id}>{mention.surface_value}{mention.normalized_value && mention.normalized_value !== mention.surface_value ? ` → ${mention.normalized_value}` : ''}</li>)}</ul>}
        </article>;
      })}
    </div>}
  </section>;
}
