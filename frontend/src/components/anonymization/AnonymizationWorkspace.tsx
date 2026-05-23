import { useMemo, useState } from 'react';
import { addDocumentMapping, deleteDocumentMapping, mergeDocumentMappings, reanonymizeDocument, repairPlaceholders, saveAnonymization, updateDocumentMapping } from '../../api/casesApi';
import type { EntityMapping } from '../../api/types';
import { DATE_PURPOSE_LABELS, ENTITY_TYPE_OPTIONS, getEntityTypeLabel, getSourceLabel, LOCATION_PURPOSE_LABELS, PERSON_ROLE_LABELS, REDACTION_DECISION_LABELS } from '../../constants/anonymizationLabels';
import RichDocumentEditor from '../documents/RichDocumentEditor';

type Props = { documentId: string; caseId?: string; initialData?: any; onSaved?: () => void; sourceContent?: unknown; sourceText?: string };
const mappingsFrom = (data: any): EntityMapping[] => data?.mappings || data?.entity_mappings || data?.anonymization?.mappings || [];
const textFrom = (data: any) => data?.anonymized_text || data?.anonymization?.anonymized_text || data?.anonymized_plain_text || '';
const contentFrom = (data: any) => data?.anonymized_content || null;

export default function AnonymizationWorkspace({ documentId, initialData, sourceContent, sourceText }: Props) {
  const [mappings, setMappings] = useState<EntityMapping[]>(mappingsFrom(initialData));
  const [selectedText, setSelectedText] = useState('');
  const [entityType, setEntityType] = useState('PERSON_FULL_NAME');
  const [tab, setTab] = useState<'REDACT'|'KEEP'|'REVIEW'>('REDACT');
  const [anonymizedText, setAnonymizedText] = useState(textFrom(initialData));
  const [anonymizedContent, setAnonymizedContent] = useState<any>(contentFrom(initialData));
  const [warning, setWarning] = useState('');

  const withId = useMemo(() => mappings.map((m, i) => ({ ...m, id: m.id || `m-${i}` })), [mappings]);
  const grouped = useMemo(() => ({ REDACT: withId.filter(m => (m.redaction_decision || 'REDACT')==='REDACT'), KEEP: withId.filter(m => m.redaction_decision==='KEEP'), REVIEW: withId.filter(m => m.redaction_decision==='REVIEW') }), [withId]);
  const conflicts = useMemo(() => { const map = new Map<string, number>(); withId.forEach((m) => { if (!m.placeholder) return; map.set(m.placeholder, (map.get(m.placeholder)||0)+1); }); return new Set([...map.entries()].filter(([,count])=>count>1).map(([key])=>key)); }, [withId]);

  const add = async () => { if (!selectedText) return; const res = await addDocumentMapping(documentId, { original_value: selectedText, entity_type: entityType, mode: 'new' }); setMappings(mappingsFrom(res.data)); setWarning('После изменения таблицы соответствия выполните повторное обезличивание.'); };
  const reanon = async () => { const res = await reanonymizeDocument(documentId, { mappings }); setMappings(mappingsFrom(res.data)); setAnonymizedText(textFrom(res.data)); setAnonymizedContent(contentFrom(res.data)); setWarning(''); };

  return <div className='anonymization-workspace'>
    <div className='redaction-mode-card'><h3>Режим обезличивания</h3><select><option value='NORMATIVE'>Нормативный режим публикации судебного акта</option><option value='EXTENDED_SAFE'>Расширенный безопасный режим</option></select><p>После смены режима необходимо повторно выполнить обезличивание.</p></div>
    {warning && <p className='warning-message'>{warning}</p>}
    {conflicts.size>0 && <div className='error-message'>Обнаружен конфликт условных обозначений: одно обозначение используется для разных сущностей. Разные сущности не могут иметь одно условное обозначение. Используйте объединение только для вариантов одного человека или объекта.</div>}
    <button className='button danger-button' type='button' onClick={async()=>{await repairPlaceholders(documentId);}}>Исправить обозначения автоматически</button>
    <RichDocumentEditor value={anonymizedContent || anonymizedText} editable onSelectionChange={setSelectedText} onChange={()=>setWarning('После изменения исходного текста необходимо повторное обезличивание.')} />
    <section className='selection-panel'><h3>Выделенный фрагмент</h3><textarea readOnly value={selectedText} /><div className='form-grid'><select value={entityType} onChange={(e)=>setEntityType(e.target.value)}>{ENTITY_TYPE_OPTIONS.map((o)=><option key={o.value} value={o.value}>{o.label}</option>)}</select><button type='button' className='button' onClick={add}>Создать новую скрываемую сущность</button></div></section>
    <div className='entity-tabs'><button className='button button-secondary' onClick={()=>setTab('REDACT')}>Обезличено</button><button className='button button-secondary' onClick={()=>setTab('KEEP')}>Оставлено в тексте</button><button className='button button-secondary' onClick={()=>setTab('REVIEW')}>Требует проверки</button></div>
    <table className={`mapping-table ${tab==='KEEP'?'kept-entities-table':''} ${tab==='REVIEW'?'review-entities-table':''}`}><thead><tr><th>Условное обозначение</th><th>Основное значение</th><th>Варианты</th><th>Тип</th><th>Роль/контекст</th><th>Решение</th><th>Причина</th><th>Источник</th><th>Действия</th></tr></thead><tbody>{grouped[tab].map((m)=><tr key={m.id} className={m.placeholder && conflicts.has(m.placeholder)?'placeholder-conflict':''}><td>{m.placeholder||'—'}</td><td>{m.original_value}</td><td><ul className='alias-list'>{(m.aliases||[]).map((a,i)=><li key={i}>{a}</li>)}</ul></td><td>{getEntityTypeLabel(m.entity_type)}</td><td>{PERSON_ROLE_LABELS[m.role || ''] || m.context || DATE_PURPOSE_LABELS[m.date_purpose || ''] || LOCATION_PURPOSE_LABELS[m.location_purpose || ''] || '—'}</td><td><span className={`decision-badge decision-${(m.redaction_decision||'REDACT').toLowerCase()}`}>{REDACTION_DECISION_LABELS[m.redaction_decision || 'REDACT']}</span></td><td>{m.redaction_reason || m.ambiguity_reason || 'Подлежит обезличиванию'}</td><td>{getSourceLabel(m.source || m.detection_method)}</td><td><button className='button button-secondary' onClick={async()=>{ await updateDocumentMapping(documentId,m.id!,{placeholder:m.placeholder||'',original_value:m.original_value,entity_type:m.entity_type});}}>Изменить</button><button className='danger-button' onClick={async()=>{await deleteDocumentMapping(documentId,m.id!);}}>Удалить</button>{tab==='REVIEW'&&<><button className='button'>Скрыть</button><button className='button button-secondary'>Оставить</button></>} </td></tr>)} </tbody></table>
    <p>После объединения выбранные варианты будут считаться одним лицом или объектом и получат одно условное обозначение.</p>
    <button className='button button-secondary' onClick={async()=>{ if(withId.length>1){await mergeDocumentMappings(documentId,{target_mapping_id:withId[0].id!,source_mapping_ids:withId.slice(1,2).map(m=>m.id!)});} }}>Объединить с существующим лицом</button>
    <button className='button button-secondary' onClick={reanon}>Повторно обезличить</button>
    <button className='button' onClick={async()=>{await saveAnonymization(documentId,{anonymized_text:anonymizedText,mappings});}}>Сохранить документ</button>
    {sourceText && <p className='warning-message'>Исходный текст изменён. Таблица соответствия может быть неактуальна. Выполните обезличивание повторно.</p>}
  </div>;
}
