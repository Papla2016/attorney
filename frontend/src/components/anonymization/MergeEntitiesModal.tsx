import type { RedactionEntity } from '../../api/types';
import { getEntityTypeLabel } from '../../constants/anonymizationLabels';

type Props = {
  entities: RedactionEntity[];
  selectedIds: string[];
  targetId: string;
  busy: boolean;
  error?: string;
  onTargetChange: (id: string) => void;
  onMerge: () => void;
  onClear: () => void;
};

export default function MergeEntitiesModal({ entities, selectedIds, targetId, busy, error, onTargetChange, onMerge, onClear }: Props) {
  if (selectedIds.length < 2) return null;
  const selected = entities.filter((entity) => selectedIds.includes(entity.entity_id));
  return <div className='merge-toolbar'>
    <div>
      <strong>Выбрано записей: {selected.length}</strong>
      <p className='muted-text'>Выберите основную запись. Остальные сущности будут присоединены к ней.</p>
    </div>
    <label>Основная запись
      <select value={targetId} onChange={(e) => onTargetChange(e.target.value)}>
        <option value=''>Выберите запись</option>
        {selected.map((entity) => <option key={entity.entity_id} value={entity.entity_id}>{entity.placeholder || 'Без обозначения'} — {entity.canonical_value} — {getEntityTypeLabel(entity.entity_class)}</option>)}
      </select>
    </label>
    {error && <p className='error-message'>{error}</p>}
    <div className='mapping-actions'>
      <button type='button' className='button' disabled={busy || !targetId} onClick={onMerge}>{busy ? 'Объединяем...' : 'Объединить'}</button>
      <button type='button' className='button button-secondary' disabled={busy} onClick={onClear}>Отменить выбор</button>
    </div>
  </div>;
}
