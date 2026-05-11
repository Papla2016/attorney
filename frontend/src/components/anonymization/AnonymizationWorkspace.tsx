import { useState } from 'react';
import { Link } from 'react-router-dom';
import { addDocumentMapping, reanonymizeDocument, saveAnonymization } from '../../api/casesApi';
import type { EntityMapping } from '../../api/types';

const ENTITY_TYPES = ['PERSON_FULL_NAME','ADDRESS','PHONE','EMAIL','PASSPORT','SNILS','INN','BIRTH_DATE','ORGANIZATION','LOCATION','OTHER'];
const val = (v: any) => v || '—';
const mappingsFrom = (data: any): EntityMapping[] => data?.mappings || data?.entity_mappings || data?.anonymization?.mappings || [];
const textFrom = (data: any) => data?.anonymized_text || data?.anonymization?.anonymized_text || data?.document?.anonymized_text || '';

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

  const placeholders = Array.from(new Set(mappings.map((m) => m.placeholder).filter(Boolean)));
  const captureSelection = () => {
    const selection = window.getSelection()?.toString().trim() || '';
    if (!selection) { setError('Выделите фрагмент обезличенного текста.'); return; }
    setSelectedText(selection);
    setError('');
  };
  const addMapping = async () => {
    if (!selectedText) { setError('Сначала добавьте выделение.'); return; }
    if (mode === 'existing' && !placeholder) { setError('Выберите существующий placeholder.'); return; }
    setBusy('mapping'); setError(''); setMessage('');
    try {
      const res = await addDocumentMapping(documentId, { original_value: selectedText, entity_type: entityType, mode, ...(mode === 'existing' ? { placeholder } : {}) });
      const nextMappings = mappingsFrom(res.data);
      setMappings(nextMappings.length ? nextMappings : [...mappings, { original_value: selectedText, entity_type: entityType, placeholder: mode === 'existing' ? placeholder : (res.data?.placeholder || 'NEW_PLACEHOLDER') }]);
      setAnonymizedText(textFrom(res.data) || anonymizedText);
      setSelectedText('');
      setMessage('Элемент добавлен в таблицу соответствия.');
    } catch {
      setError('Не удалось добавить элемент в таблицу соответствия.');
    } finally { setBusy(''); }
  };
  const reanonymize = async () => {
    setBusy('reanonymize'); setError(''); setMessage('');
    try {
      const res = await reanonymizeDocument(documentId, { mappings });
      setAnonymizedText(textFrom(res.data) || anonymizedText);
      const nextMappings = mappingsFrom(res.data);
      if (nextMappings.length) setMappings(nextMappings);
      setMessage('Документ повторно обезличен.');
    } catch { setError('Не удалось повторно обезличить документ.'); }
    finally { setBusy(''); }
  };
  const save = async () => {
    setBusy('save'); setError(''); setMessage('');
    try {
      await saveAnonymization(documentId, { anonymized_text: anonymizedText, mappings });
      setMessage('Документ сохранён');
      onSaved?.();
    } catch { setError('Не удалось сохранить документ.'); }
    finally { setBusy(''); }
  };

  return <div className='anonymization-workspace'>
    {message && <p className='success-message'>{message}</p>}{error && <p className='error-message'>{error}</p>}
    <section className='anonymized-text-panel'>
      <h2>Обезличенный текст</h2>
      {anonymizedText ? <pre>{anonymizedText}</pre> : <p className='empty-state'>Обезличенный текст пока не готов.</p>}
      <div className='mapping-actions'><button type='button' className='button button-secondary' onClick={captureSelection}>Добавить выделение в таблицу соответствия</button></div>
    </section>
    <section className='selection-panel'>
      <h3>Ручная разметка</h3>
      <label>Выделенный текст</label><textarea readOnly rows={3} value={selectedText} />
      <div className='form-grid'><div><label>Тип сущности</label><select value={entityType} onChange={(e) => setEntityType(e.target.value)}>{ENTITY_TYPES.map((type) => <option key={type} value={type}>{type}</option>)}</select></div><div><label>Режим</label><select value={mode} onChange={(e) => setMode(e.target.value as 'new' | 'existing')}><option value='new'>Новый placeholder</option><option value='existing'>Использовать существующий placeholder</option></select></div>{mode === 'existing' && <div><label>Placeholder</label><select value={placeholder} onChange={(e) => setPlaceholder(e.target.value)}><option value=''>Выберите placeholder</option>{placeholders.map((p) => <option key={p} value={p}>{p}</option>)}</select></div>}</div>
      <button type='button' className='button' disabled={busy === 'mapping'} onClick={addMapping}>Добавить mapping</button>
    </section>
    <section>
      <h2>Таблица соответствия</h2>
      <div className='table-card'><table className='mapping-table'><thead><tr><th>placeholder</th><th>исходное значение</th><th>тип сущности</th><th>источник</th></tr></thead><tbody>{mappings.map((m, idx) => <tr key={`${m.placeholder}-${idx}`}><td>{val(m.placeholder)}</td><td>{val(m.original_value)}</td><td>{val(m.entity_type)}</td><td>{val(m.source)}</td></tr>)}{mappings.length === 0 && <tr><td colSpan={4}>Таблица соответствия пуста.</td></tr>}</tbody></table></div>
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
