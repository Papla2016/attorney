import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { uploadDoc } from '../../api/casesApi';
import AppLayout from '../../components/layout/AppLayout';

export default function UploadDocumentPage() {
  const { caseId = '' } = useParams();
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState('');
  return <AppLayout><div className='card form-card'><h1>Загрузка документа</h1>{error && <p className='error-message'>{error}</p>}<form onSubmit={async (e:any)=>{e.preventDefault(); setError(''); const f=new FormData(e.currentTarget); try{ const res = await uploadDoc(caseId,{title:String(f.get('title')),act_type:String(f.get('act_type')),text:String(f.get('text'))}); setResult(res.data);}catch(er:any){ if(er?.response?.status===403) setError('Недостаточно прав'); else if(er?.response?.status>=500) setError('Внутренняя ошибка сервера'); else if(er?.message==='Network Error') setError('Не удалось подключиться к серверу'); else setError('Не удалось выполнить действие'); } }}>
  <label>Название документа</label><input name='title'/><label>Тип судебного акта</label><select name='act_type'><option value='DECISION'>решение</option><option value='SENTENCE'>приговор</option><option value='RULING'>постановление</option><option value='DETERMINATION'>определение</option><option value='COURT_ORDER'>судебный приказ</option><option value='OTHER'>другое</option></select><label>Текст документа</label><textarea rows={10} name='text'/><button className='button'>Загрузить и обезличить</button></form>
  {result && <div className='card'><p>document_id: {result.document_id}</p><p>anonymization_job_id: {result.anonymization_job_id}</p><p>status: {result.status}</p>{result.document_id && <Link to={`/documents/${result.document_id}`}>Публичный документ</Link>}<br/><Link to={`/staff/cases/${caseId}`}>Назад к делу</Link></div>}</div></AppLayout>;
}
