import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  addDocumentMapping,
  deleteDocumentMapping,
  mergeDocumentMappings,
  reanonymizeDocument,
  saveAnonymization,
  updateDocumentMapping
} from '../../api/casesApi';
import type { EntityMapping } from '../../api/types';
import { ENTITY_TYPE_OPTIONS, getEntityTypeLabel, getSourceLabel } from '../../constants/anonymizationLabels';

const val = (v: any) => v || '—';
const mappingsFrom = (data: any): EntityMapping[] => data?.mappings || data?.entity_mappings || data?.anonymization?.mappings || [];
const textFrom = (data: any) => data?.anonymized_text || data?.anonymization?.anonymized_text || data?.document?.anonymized_text || '';
const notSupportedMessage = 'Backend пока не поддерживает изменение таблицы соответствия.';

type Props = { documentId: string; caseId?: string; initialData?: any; onSaved?: () => void };

export default function AnonymizationWorkspace({ documentId, caseId, initialData, onSaved }: Props) {
  const [anonymizedText, setAnonymizedText] = useState(textFrom(initialData));
  const [mappings, setMappings] = useState<EntityMapping[]>(mappingsFrom(initialData));
  const [selectedText, setSelectedText] = useState('');
  const [entityType, setEntityType] = useState('PERSON_FULL_NAME');
  const [mode, setMode] = useState<'new' | 'existing'>('new');
  const [placeholder, setPlaceholder] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState('');
  const [editId, setEditId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState({ placeholder: '', original_value: '', entity_type: 'PERSON_FULL_NAME' });
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [mergeTargetId, setMergeTargetId] = useState('');
  const [hasUnsavedMappingChanges, setHasUnsavedMappingChanges] = useState(false);

  const placeholders = Array.from(new Set(mappings.map((m) => m.placeholder).filter(Boolean)));
  const mappingsWithId = useMemo(() => mappings.map((m, idx) => ({ ...m, id: m.id || `${m.placeholder || 'm'}-${idx}` })), [mappings]);

  const handleApiError = (fallback: string, e: any) => {
    if (e?.response?.status === 404 || e?.response?.status === 405) setError(notSupportedMessage);
    else setError(fallback);
  };

  const captureSelection = () => {
    const selection = window.getSelection()?.toString().trim() || '';
    if (!selection) { setError('Выделите фрагмент обезличенного текста.'); return; }
    setSelectedText(selection);
    setError('');
  };

  const addMapping = async () => {
    if (!selectedText) { setError('Сначала добавьте выделение.'); return; }
    if (mode === 'existing' && !placeholder) { setError('Выберите существующее обозначение.'); return; }
    setBusy('mapping'); setError(''); setMessage('');
    try {
      const res = await addDocumentMapping(documentId, { original_value: selectedText, entity_type: entityType, mode, ...(mode === 'existing' ? { placeholder } : {}) });
      const nextMappings = mappingsFrom(res.data);
      setMappings(nextMappings.length ? nextMappings : [...mappings, { original_value: selectedText, entity_type: entityType, placeholder: mode === 'existing' ? placeholder : (res.data?.placeholder || 'ФИО1') }]);
      setAnonymizedText(textFrom(res.data) || anonymizedText);
      setSelectedText('');
      setHasUnsavedMappingChanges(true);
      setMessage('Элемент добавлен в таблицу соответствия.');
    } catch (e) {
      handleApiError('Не удалось добавить элемент в таблицу соответствия.', e);
    } finally { setBusy(''); }
  };

  const startEdit = (m: EntityMapping & { id: string }) => {
    setEditId(m.id);
    setEditForm({ placeholder: m.placeholder || '', original_value: m.original_value || '', entity_type: m.entity_type || 'PERSON_FULL_NAME' });
  };

  const saveEdit = async () => {
    if (!editId) return;
    setBusy('edit'); setError(''); setMessage('');
    try {
      const res = await updateDocumentMapping(documentId, editId, editForm);
      const nextMappings = mappingsFrom(res.data);
      setMappings(nextMappings.length ? nextMappings : mappings.map((m, idx) => ((m.id || `${m.placeholder || 'm'}-${idx}`) === editId ? { ...m, ...editForm } : m)));
      setEditId(null);
      setHasUnsavedMappingChanges(true);
      setMessage('Элемент таблицы соответствия обновлён.');
    } catch (e) {
      handleApiError('Не удалось изменить элемент таблицы соответствия.', e);
    } finally { setBusy(''); }
  };

  const deleteMapping = async (mappingId: string) => {
    if (!window.confirm('Удалить элемент из таблицы соответствия? После удаления рекомендуется выполнить повторное обезличивание.')) return;
    setBusy(`delete-${mappingId}`); setError(''); setMessage('');
    try {
      await deleteDocumentMapping(documentId, mappingId);
      setMappings(mappingsWithId.filter((m) => m.id !== mappingId));
      setSelectedIds((prev) => prev.filter((id) => id !== mappingId));
      if (mergeTargetId === mappingId) setMergeTargetId('');
      setHasUnsavedMappingChanges(true);
      setMessage('Элемент удалён из таблицы соответствия.');
    } catch (e) {
      handleApiError('Не удалось удалить элемент таблицы соответствия.', e);
    } finally { setBusy(''); }
  };

  const mergeMappings = async () => {
    if (selectedIds.length < 2) { setError('Выберите минимум две записи для объединения.'); return; }
    if (!mergeTargetId) { setError('Выберите основную запись, в которую нужно объединить остальные.'); return; }
    const sourceIds = selectedIds.filter((id) => id !== mergeTargetId);
    if (!sourceIds.length) { setError('Выберите минимум две записи для объединения.'); return; }
    setBusy('merge'); setError(''); setMessage('');
    try {
      const res = await mergeDocumentMappings(documentId, { target_mapping_id: mergeTargetId, source_mapping_ids: sourceIds });
      setMappings(mappingsFrom(res.data));
      setSelectedIds([]);
      setMergeTargetId('');
      setHasUnsavedMappingChanges(true);
      setMessage('Записи таблицы соответствия объединены. Теперь можно выполнить повторное обезличивание.');
    } catch (e) {
      handleApiError('Не удалось объединить элементы таблицы соответствия.', e);
    } finally { setBusy(''); }
  };

  const reanonymize = async () => {
    setBusy('reanonymize'); setError(''); setMessage('');
    try {
      const res = await reanonymizeDocument(documentId, { mappings });
      setAnonymizedText(textFrom(res.data) || anonymizedText);
      const nextMappings = mappingsFrom(res.data);
      if (nextMappings.length) setMappings(nextMappings);
      setHasUnsavedMappingChanges(false);
      setMessage('Документ повторно обезличен с учётом изменений таблицы соответствия.');
    } catch (e) { handleApiError('Не удалось повторно обезличить документ.', e); }
    finally { setBusy(''); }
  };

  const save = async () => {
    if (hasUnsavedMappingChanges && !window.confirm('Таблица соответствия изменена, но повторное обезличивание не выполнено. Сохранить без повторного обезличивания?')) return;
    setBusy('save'); setError(''); setMessage('');
    try {
      await saveAnonymization(documentId, { anonymized_text: anonymizedText, mappings });
      setMessage('Документ сохранён.');
      onSaved?.();
    } catch (e) { handleApiError('Не удалось сохранить документ.', e); }
    finally { setBusy(''); }
  };

  return <div className='anonymization-workspace'>
    {message && <p className='success-message'>{message}</p>}{error && <p className='error-message'>{error}</p>}
    {hasUnsavedMappingChanges && <div className='warning-message'>Таблица соответствия изменена. Для применения изменений к тексту выполните повторное обезличивание.</div>}
    <section className='anonymized-text-panel'>
      <h2>Обезличенный текст</h2>
      {anonymizedText ? <pre>{anonymizedText}</pre> : <p className='empty-state'>Обезличенный текст пока не готов.</p>}
      <div className='mapping-actions'><button type='button' className='button button-secondary' onClick={captureSelection}>Добавить выделение в таблицу соответствия</button></div>
    </section>
    <section className='selection-panel'>
      <h3>Ручная разметка</h3>
      <label>Выделенный текст</label><textarea readOnly rows={3} value={selectedText} />
      <div className='form-grid'><div><label>Тип сущности</label><select value={entityType} onChange={(e) => setEntityType(e.target.value)}>{ENTITY_TYPE_OPTIONS.map((type) => <option key={type.value} value={type.value}>{type.label}</option>)}</select></div><div><label>Режим</label><select value={mode} onChange={(e) => setMode(e.target.value as 'new' | 'existing')}><option value='new'>Новое условное обозначение</option><option value='existing'>Использовать существующее обозначение</option></select></div>{mode === 'existing' && <div><label>Условное обозначение</label><select value={placeholder} onChange={(e) => setPlaceholder(e.target.value)}><option value=''>Выберите обозначение</option>{placeholders.map((p) => <option key={p} value={p}>{p}</option>)}</select></div>}</div>
      <button type='button' className='button' disabled={busy === 'mapping'} onClick={addMapping}>Добавить в таблицу соответствия</button>
    </section>
    <section>
      <h2>Таблица соответствия</h2>
      <div className='mapping-merge-panel'>
        <h3>Объединение записей</h3>
        <p>Выбранные элементы: {selectedIds.length}</p>
        <label>Целевое условное обозначение</label>
        <select value={mergeTargetId} onChange={(e) => setMergeTargetId(e.target.value)}>
          <option value=''>Выберите основную запись</option>
          {mappingsWithId.filter((m) => selectedIds.includes(m.id)).map((m) => <option key={m.id} value={m.id}>{m.placeholder} — {m.original_value}</option>)}
        </select>
        <button type='button' className='button button-secondary' disabled={busy === 'merge'} onClick={mergeMappings}>Объединить выбранные</button>
      </div>
      <div className='table-card'><table className='mapping-table'><thead><tr><th></th><th>Условное обозначение</th><th>Исходное значение</th><th>Тип данных</th><th>Способ обнаружения</th><th>Действия</th></tr></thead><tbody>{mappingsWithId.map((m) => <tr className={selectedIds.includes(m.id) ? 'selected-row' : ''} key={m.id}><td><input type='checkbox' checked={selectedIds.includes(m.id)} onChange={(e) => setSelectedIds((prev) => e.target.checked ? [...prev, m.id] : prev.filter((id) => id !== m.id))} /></td><td>{val(m.placeholder)}</td><td className='mapping-original'>{val(m.original_value)}</td><td><span className='entity-badge'>{getEntityTypeLabel(m.entity_type)}</span></td><td><span className='source-badge'>{getSourceLabel(m.source)}</span></td><td>{editId === m.id ? <div className='mapping-edit-form'><label>Условное обозначение</label><input value={editForm.placeholder} onChange={(e) => setEditForm((prev) => ({ ...prev, placeholder: e.target.value }))} /><label>Исходное значение</label><textarea rows={3} value={editForm.original_value} onChange={(e) => setEditForm((prev) => ({ ...prev, original_value: e.target.value }))} /><label>Тип данных</label><select value={editForm.entity_type} onChange={(e) => setEditForm((prev) => ({ ...prev, entity_type: e.target.value }))}>{ENTITY_TYPE_OPTIONS.map((type) => <option key={type.value} value={type.value}>{type.label}</option>)}</select><div className='mapping-actions'><button type='button' className='button' disabled={busy === 'edit'} onClick={saveEdit}>Сохранить</button><button type='button' className='button button-secondary' onClick={() => setEditId(null)}>Отмена</button></div></div> : <div className='mapping-actions'><button type='button' className='button button-secondary' onClick={() => startEdit(m)}>Изменить</button><button type='button' className='button danger-button' disabled={busy === `delete-${m.id}`} onClick={() => deleteMapping(m.id)}>Удалить</button></div>}</td></tr>)}{mappingsWithId.length === 0 && <tr><td colSpan={6}>Таблица соответствия пуста.</td></tr>}</tbody></table></div>
    </section>
    <section className='document-actions'>
      <p>Повторное обезличивание применяет ручную таблицу соответствия и заново обрабатывает документ.</p>
      <button type='button' className='button button-secondary' disabled={!documentId || mappings.length === 0 || busy === 'reanonymize'} onClick={reanonymize}>Повторно обезличить</button>
      <button type='button' className='button' disabled={!documentId || busy === 'save'} onClick={save}>Сохранить документ</button>
      {caseId && <><Link className='button button-secondary' to={`/staff/cases/${caseId}`}>Назад к делу</Link><Link className='button button-secondary' to={`/staff/cases/${caseId}`}>Открыть дело</Link></>}
      <Link className='button button-secondary' to={`/documents/${documentId}`}>Открыть публичную версию</Link>
    </section>
  </div>;
}
