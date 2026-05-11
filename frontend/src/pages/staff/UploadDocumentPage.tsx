import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { getDocumentAnonymization, uploadDoc } from '../../api/casesApi';
import AppLayout from '../../components/layout/AppLayout';
import AnonymizationWorkspace from '../../components/anonymization/AnonymizationWorkspace';

const documentIdFrom = (data: any) => data?.document_id || data?.id || data?.document?.id;
const hasAnonymization = (data: any) => Boolean(data?.anonymized_text || data?.mappings || data?.entity_mappings || data?.anonymization);

export default function UploadDocumentPage() {
  const { caseId = '' } = useParams();
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  return <AppLayout><div className='card form-card'><h1>Загрузка документа</h1>{error && <p className='error-message'>{error}</p>}<form onSubmit={async (e:any)=>{e.preventDefault(); setError(''); setLoading(true); const f=new FormData(e.currentTarget); try{ const res = await uploadDoc(caseId,{title:String(f.get('title')),act_type:String(f.get('act_type')),text:String(f.get('text'))}); let next = res.data; const id = documentIdFrom(next); if (id && !hasAnonymization(next)) { try { const anon = await getDocumentAnonymization(id); next = { ...next, ...anon.data }; } catch { /* backend may still be processing */ } } setResult(next);}catch(er:any){ if(er?.response?.status===403) setError('Недостаточно прав'); else if(er?.response?.status>=500) setError('Внутренняя ошибка сервера'); else if(er?.message==='Network Error') setError('Не удалось подключиться к серверу'); else setError('Не удалось выполнить действие'); } finally { setLoading(false); } }}>
  <label>Название документа</label><input name='title' required/><label>Тип судебного акта</label><select name='act_type'><option value='DECISION'>решение</option><option value='SENTENCE'>приговор</option><option value='RULING'>постановление</option><option value='DETERMINATION'>определение</option><option value='COURT_ORDER'>судебный приказ</option><option value='OTHER'>другое</option></select><label>Текст документа</label><textarea rows={10} name='text' required/><button className='button' disabled={loading}>{loading ? 'Обезличивание...' : 'Загрузить и обезличить'}</button></form>
  {result && <div className='card'><p>document_id: {documentIdFrom(result)}</p><p>anonymization_job_id: {result.anonymization_job_id || '—'}</p><p>status: {result.status || '—'}</p><Link to={`/staff/documents/${documentIdFrom(result)}/anonymization`}>Открыть ручную проверку</Link><br/><Link to={`/staff/cases/${caseId}`}>Назад к делу</Link></div>}
  {result && documentIdFrom(result) && <AnonymizationWorkspace key={documentIdFrom(result)} documentId={documentIdFrom(result)} caseId={caseId} initialData={result} />}</div></AppLayout>;
}
