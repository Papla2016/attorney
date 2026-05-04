import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { createCase } from '../../api/casesApi';
import AppLayout from '../../components/layout/AppLayout';
import { getApiErrorMessage } from '../../utils/errors';

export default function CreateCasePage() {
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const nav = useNavigate();
  return <AppLayout><div className='card form-card'><h1>Создание дела</h1>{message && <p className='success-message'>{message}</p>}{error && <p className='error-message'>{error}</p>}<form onSubmit={async (e:any)=>{e.preventDefault(); setError(''); const f=new FormData(e.currentTarget); const payload={court_id:String(f.get('court_id')||''),case_number:String(f.get('case_number')||''),document_number:String(f.get('document_number')||''),document_date:String(f.get('document_date')||''),instance:String(f.get('instance')||''),region:String(f.get('region')||''),law_article:String(f.get('law_article')||''),practice_topic:String(f.get('practice_topic')||''),judges:String(f.get('judges')||'').split(',').map((x)=>x.trim()).filter(Boolean)}; try{ const res=await createCase(payload as any); setMessage('Дело создано'); nav(`/staff/cases/${res.data?.id || ''}`);}catch(er:any){ if(er?.response?.status===403) setError('Недостаточно прав для создания дела'); else if(er?.response?.status>=500) setError('Внутренняя ошибка сервера'); else setError(getApiErrorMessage(er)); } }}>
  <label>ID суда</label><input name='court_id'/><label>Номер дела</label><input name='case_number'/><label>Номер документа</label><input name='document_number'/><label>Дата документа</label><input type='date' name='document_date'/><label>Инстанция</label><select name='instance'><option value='FIRST'>первая инстанция</option><option value='APPEAL'>апелляционная инстанция</option><option value='CASSATION'>кассационная инстанция</option><option value='SUPERVISION'>надзорная инстанция</option><option value='NEW_OR_NEWLY_DISCOVERED'>пересмотр по новым или вновь открывшимся обстоятельствам</option></select><label>Регион</label><input name='region'/><label>Статья закона</label><input name='law_article'/><label>Судебная практика</label><input name='practice_topic'/><label>Судьи дела</label><input name='judges' placeholder='через запятую'/><button className='button'>Создать дело</button></form></div></AppLayout>;
}
