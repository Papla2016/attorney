import { useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { getDocumentAnonymization, uploadDoc } from '../../api/casesApi';
import AppLayout from '../../components/layout/AppLayout';
import AnonymizationWorkspace from '../../components/anonymization/AnonymizationWorkspace';
import RichDocumentEditor from '../../components/documents/RichDocumentEditor';
import CourtDocumentView from '../../components/documents/CourtDocumentView';

const documentIdFrom = (data: any) => data?.document_id || data?.id || data?.document?.id;
const hasAnonymization = (data: any) => Boolean(data?.anonymized_text || data?.mappings || data?.entity_mappings || data?.anonymization);

export default function UploadDocumentPage() {
  const { caseId = '' } = useParams();
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [source, setSource] = useState<any>({ type: 'doc', content: [{ type: 'paragraph', content: [{ type: 'text', text: '' }] }] });
  const [sourceText, setSourceText] = useState('');
  const [tab, setTab] = useState<'editor'|'preview'|'md'>('editor');
  const [mdMode, setMdMode] = useState<'src'|'preview'>('preview');
  const markdownText = useMemo(() => sourceText.split('\n').map((line) => line ? line : '').join('\n\n'), [sourceText]);
  return <AppLayout><div className='card form-card'><h1>Загрузка документа</h1>{error && <p className='error-message'>{error}</p>}
  <form onSubmit={async (e:any)=>{e.preventDefault(); setError(''); setLoading(true); const f=new FormData(e.currentTarget); try{ const res = await uploadDoc(caseId,{title:String(f.get('title')),act_type:String(f.get('act_type')),content_format:'TIPTAP_JSON',content:source,text:sourceText}); let next = res.data; const id = documentIdFrom(next); if (id && !hasAnonymization(next)) { try { const anon = await getDocumentAnonymization(id); next = { ...next, ...anon.data }; } catch {} } setResult(next);}catch(er:any){ setError('Не удалось выполнить действие'); } finally { setLoading(false); } }}>
  <label>Название документа</label><input name='title' required/><label>Тип судебного акта</label><select name='act_type'><option value='DECISION'>решение</option><option value='SENTENCE'>приговор</option><option value='RULING'>постановление</option><option value='DETERMINATION'>определение</option><option value='COURT_ORDER'>судебный приказ</option><option value='OTHER'>другое</option></select>
  <div className='editor-tabs'><button type='button' className='button button-secondary' onClick={()=>setTab('editor')}>Редактор</button><button type='button' className='button button-secondary' onClick={()=>setTab('preview')}>Предпросмотр документа</button><button type='button' className='button button-secondary' onClick={()=>setTab('md')}>Markdown / GitHub-предпросмотр</button></div>
  {tab==='editor' && <RichDocumentEditor value={source} onChange={({json,text})=>{setSource(json);setSourceText(text);}} />}
  {tab==='preview' && <div className='preview-tab'><CourtDocumentView document={{id:'draft',title:String((new FormData(document.querySelector('form')||undefined as any).get('title'))||'Черновик'),anonymized_text:sourceText}} /></div>}
  {tab==='md' && <div className='markdown-preview'><div className='form-row'><button type='button' className='button button-secondary' onClick={()=>setMdMode('src')}>Исходная разметка</button><button type='button' className='button button-secondary' onClick={()=>setMdMode('preview')}>Предпросмотр</button></div>{mdMode==='src'?<textarea rows={12} value={markdownText} readOnly/>:<ReactMarkdown remarkPlugins={[remarkGfm]}>{markdownText}</ReactMarkdown>}<p className='warning-message'>Markdown-предпросмотр не отображает все свойства форматирования документа, например сложное выравнивание и часть визуальных стилей.</p></div>}
  <button className='button' disabled={loading}>{loading ? 'Обезличивание...' : 'Загрузить и обезличить'}</button></form>
  {result && documentIdFrom(result) && <AnonymizationWorkspace key={documentIdFrom(result)} documentId={documentIdFrom(result)} caseId={caseId} initialData={result} sourceContent={source} sourceText={sourceText} />}</div></AppLayout>;
}
