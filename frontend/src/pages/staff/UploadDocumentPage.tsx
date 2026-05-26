import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { getDocumentAnonymization, uploadDoc } from '../../api/casesApi';
import AppLayout from '../../components/layout/AppLayout';
import AnonymizationWorkspace from '../../components/anonymization/AnonymizationWorkspace';
import RichDocumentEditor from '../../components/documents/RichDocumentEditor';
import CourtDocumentView from '../../components/documents/CourtDocumentView';
import { plainTextToTiptapDocument } from '../../utils/tiptapDocument';

const documentIdFrom = (data: any) => data?.document_id || data?.id || data?.document?.id;
const hasAnonymization = (data: any) => Boolean(data?.anonymized_text || data?.mappings || data?.entity_mappings || data?.anonymization);

export default function UploadDocumentPage() {
  const { caseId = '' } = useParams();
  const [title, setTitle] = useState('');
  const [actType, setActType] = useState('DECISION');
  const [redactionMode, setRedactionMode] = useState<'NORMATIVE'|'EXTENDED_SAFE'>('NORMATIVE');
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [source, setSource] = useState<any>(plainTextToTiptapDocument(''));
  const [sourceText, setSourceText] = useState('');
  const [tab, setTab] = useState<'editor'|'preview'>('editor');

  return <AppLayout><div className='document-upload-page'><h1>Загрузка и обезличивание судебного документа</h1>{error && <p className='error-message'>{error}</p>}
    <div className='document-info-card'><h3>Сведения о документе</h3>
      <label>Название документа</label><input value={title} onChange={(e)=>setTitle(e.target.value)} required />
      <label>Тип судебного акта</label><select value={actType} onChange={(e)=>setActType(e.target.value)}><option value='DECISION'>Решение</option><option value='SENTENCE'>Приговор</option><option value='RULING'>Постановление</option><option value='DETERMINATION'>Определение</option><option value='COURT_ORDER'>Судебный приказ</option><option value='OTHER'>Другое</option></select>
      <label>Режим обезличивания</label><select value={redactionMode} onChange={(e)=>setRedactionMode(e.target.value as any)}><option value='NORMATIVE'>Нормативный</option><option value='EXTENDED_SAFE'>Расширенный безопасный</option></select>
    </div>
    <div className='document-info-card'><h3>Текст документа</h3><div className='editor-mode-tabs'><button type='button' className='button button-secondary' onClick={()=>setTab('editor')}>Редактирование документа</button><button type='button' className='button button-secondary' onClick={()=>setTab('preview')}>Предпросмотр документа</button></div>
    {tab==='editor' && <RichDocumentEditor value={source} onChange={({json,text})=>{setSource(json);setSourceText(text);}} />}
    {tab==='preview' && <div className='preview-tab'><CourtDocumentView variant='draftPreview' title={title || 'Черновик документа'} content={source} contentFormat='TIPTAP_JSON' text={sourceText} /></div>}
    </div>
    <button className='button' disabled={loading || !title} onClick={async ()=>{ setError(''); setLoading(true); try{ const res = await uploadDoc(caseId,{title,act_type:actType,content_format:'TIPTAP_JSON',content:source,text:sourceText,publication_redaction_mode:redactionMode} as any); let next=res.data; const id=documentIdFrom(next); if(id && !hasAnonymization(next)){ try{ const anon=await getDocumentAnonymization(id); next={...next,...anon.data}; }catch{}} setResult({...next, publication_redaction_mode: next.publication_redaction_mode || redactionMode}); }catch{setError('Не удалось выполнить действие');} finally{setLoading(false);} }}> {loading ? 'Выполняется обезличивание...' : 'Выполнить обезличивание'} </button>
    {result && documentIdFrom(result) && <AnonymizationWorkspace key={documentIdFrom(result)} documentId={documentIdFrom(result)} caseId={caseId} initialData={result} sourceContent={source} sourceText={sourceText} />}
  </div></AppLayout>;
}
