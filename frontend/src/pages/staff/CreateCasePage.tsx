import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { createCase } from '../../api/casesApi';
import AppLayout from '../../components/layout/AppLayout';
import { getApiErrorMessage } from '../../utils/errors';
import { INSTANCE_OPTIONS } from '../../constants/instances';
import { RUSSIAN_REGIONS } from '../../constants/regions';
import AutocompleteInput from '../../components/ui/AutocompleteInput';
import { LEGAL_ARTICLE_OPTIONS } from '../../constants/legalArticles';
import ServerState from '../../components/ui/ServerState';

export default function CreateCasePage() {
  const [message, setMessage] = useState(''); const [error, setError] = useState<any>(null); const [loading, setLoading] = useState(false); const [lawArticle,setLawArticle]=useState('');
  const nav = useNavigate();
  return <AppLayout><div className='card form-card'><h1>Создание дела</h1>{message && <p className='success-message'>{message}</p>}<ServerState loading={loading} error={error}/><form onSubmit={async (e:any)=>{e.preventDefault(); setError(null); setLoading(true); const f=new FormData(e.currentTarget); const payload={court_id:String(f.get('court_id')||''),case_number:String(f.get('case_number')||''),document_number:String(f.get('document_number')||''),document_date:String(f.get('document_date')||''),instance:String(f.get('instance')||''),region:String(f.get('region')||''),law_article:String(f.get('law_article')||''),practice_topic:String(f.get('practice_topic')||''),judges:String(f.get('judges')||'').split(',').map((x)=>x.trim()).filter(Boolean)}; try{ const res=await createCase(payload as any); setMessage('Дело создано'); nav(`/staff/cases/${res.data?.id || ''}`);}catch(er:any){ setError(er); if(!er?.response) setMessage(getApiErrorMessage(er)); } finally { setLoading(false);} }}>
  <label>ID суда</label><input name='court_id'/><label>Номер дела</label><input required name='case_number'/><label>Номер документа</label><input name='document_number'/><label>Дата документа</label><input type='date' name='document_date'/><label>Инстанция</label><select name='instance'>{INSTANCE_OPTIONS.filter(i=>i.value).map(i=><option value={i.value} key={i.value}>{i.label}</option>)}</select><label>Регион</label><select required name='region'><option value=''>Выберите регион</option>{RUSSIAN_REGIONS.map(r=><option key={r} value={r}>{r}</option>)}</select><label>Статья закона</label><AutocompleteInput name='law_article' value={lawArticle} onChange={setLawArticle} options={LEGAL_ARTICLE_OPTIONS} /><label>Судебная практика</label><input name='practice_topic'/><label>Судьи дела</label><input name='judges' placeholder='через запятую'/><button className='button' disabled={loading}>Создать дело</button></form></div></AppLayout>;
}
