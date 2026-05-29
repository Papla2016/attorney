import { useEffect, useState } from 'react';
import type { RedactionEntity } from '../../api/types';
import { ENTITY_TYPE_OPTIONS, PERSON_ROLE_LABELS } from '../../constants/anonymizationLabels';

type Props = {
  entity: RedactionEntity | null;
  busy: boolean;
  error?: string;
  onClose: () => void;
  onSave: (payload: { canonical_value: string; entity_class: string; person_role?: string; context_label?: string }) => void;
};

export default function EntityEditorModal({ entity, busy, error, onClose, onSave }: Props) {
  const [canonicalValue, setCanonicalValue] = useState('');
  const [entityClass, setEntityClass] = useState('OTHER');
  const [personRole, setPersonRole] = useState('');
  const [contextLabel, setContextLabel] = useState('');

  useEffect(() => {
    setCanonicalValue(entity?.canonical_value || '');
    setEntityClass(entity?.entity_class || 'OTHER');
    setPersonRole(entity?.person_role || '');
    setContextLabel(entity?.context_label || entity?.context_kind || '');
  }, [entity]);

  if (!entity) return null;
  return <div className='modal-backdrop' role='presentation'>
    <form className='entity-editor-modal' onSubmit={(e) => { e.preventDefault(); onSave({ canonical_value: canonicalValue, entity_class: entityClass, person_role: entityClass === 'PERSON' ? personRole || undefined : undefined, context_label: contextLabel || undefined }); }}>
      <div className='panel-header-row'>
        <h3>Редактирование сущности</h3>
        <button type='button' className='button button-secondary' onClick={onClose} disabled={busy}>Закрыть</button>
      </div>
      <label>Условное обозначение
        <input value={entity.placeholder || '—'} readOnly />
      </label>
      <p className='muted-text'>Условное обозначение формируется системой.</p>
      <label>Основное значение
        <input value={canonicalValue} onChange={(e) => setCanonicalValue(e.target.value)} required />
      </label>
      <label>Тип данных
        <select value={entityClass} onChange={(e) => setEntityClass(e.target.value)}>
          {ENTITY_TYPE_OPTIONS.map((opt) => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
        </select>
      </label>
      {entityClass === 'PERSON' && <label>Роль лица
        <select value={personRole} onChange={(e) => setPersonRole(e.target.value)}>
          <option value=''>Не определено</option>
          {Object.entries(PERSON_ROLE_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
      </label>}
      <label>Контекст
        <input value={contextLabel} onChange={(e) => setContextLabel(e.target.value)} placeholder='Например: судья, адрес регистрации, дата заседания' />
      </label>
      {error && <p className='error-message'>{error}</p>}
      <div className='mapping-actions'>
        <button type='submit' className='button' disabled={busy}>{busy ? 'Сохраняем...' : 'Сохранить'}</button>
        <button type='button' className='button button-secondary' onClick={onClose} disabled={busy}>Отмена</button>
      </div>
    </form>
  </div>;
}
