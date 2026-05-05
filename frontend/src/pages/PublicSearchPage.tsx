import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { addFavorite, searchPublicDocuments } from '../api/casesApi';
import { Link } from 'react-router-dom';
import AppLayout from '../components/layout/AppLayout';
import { useAuth } from '../auth/useAuth';
import { isStaff } from '../utils/roles';
import { REGION_OPTIONS } from '../constants/regions';
import { INSTANCE_OPTIONS } from '../constants/instances';
import AutocompleteInput from '../components/ui/AutocompleteInput';
import { LEGAL_ARTICLE_OPTIONS } from '../constants/legalArticles';
import ServerState from '../components/ui/ServerState';

export default function PublicSearchPage() {
  const [params, setParams] = useState<any>({});
  const [legalArticle, setLegalArticle] = useState('');
  const [dateError, setDateError] = useState('');
  const { isAuthenticated, roles } = useAuth();
  const { data, isLoading, error } = useQuery({ queryKey: ['publicDocs', params], queryFn: async () => (await searchPublicDocuments(params)).data, retry: false });
  const docs = data?.items || data || [];
  return <AppLayout><section className='hero'><h1>Поиск судебных документов</h1></section>
  <div className='card form-card'><form onSubmit={(e:any)=>{e.preventDefault(); setDateError(''); const f=new FormData(e.currentTarget); const document_date_from=String(f.get('document_date_from')||''); const document_date_to=String(f.get('document_date_to')||''); if(document_date_from && document_date_to && document_date_to < document_date_from){ setDateError('Дата окончания не может быть раньше даты начала'); return; } const next:any=Object.fromEntries(f.entries()); if(next.region==='Все регионы') delete next.region; if(!next.instance) delete next.instance; setParams(next);}}>
  <label>Поиск по номеру дела, статье, суду или тексту</label><div className='form-row'><input name='q'/><button className='button'>Найти</button><button type='button' className='button button-secondary' onClick={()=>setParams({})}>Сбросить</button></div>
  <div className='form-grid'><select name='region'>{REGION_OPTIONS.map((r)=><option key={r} value={r}>{r}</option>)}</select><input name='court_name' placeholder='суд'/><input name='act_type' placeholder='тип судебного акта'/><select name='instance'>{INSTANCE_OPTIONS.map((i)=><option key={i.label} value={i.value}>{i.label}</option>)}</select><AutocompleteInput name='legal_article' value={legalArticle} onChange={setLegalArticle} options={LEGAL_ARTICLE_OPTIONS} placeholder='Статья закона' /><input name='judge' placeholder='Фамилия или ФИО судьи'/><div><label>Дата документа от</label><input name='document_date_from' type='date' placeholder='Начальная дата'/></div><div><label>Дата документа до</label><input name='document_date_to' type='date' placeholder='Конечная дата'/></div></div>
  {dateError && <p className='error-message'>{dateError}</p>}</form></div>
  <ServerState loading={isLoading} error={error} />
  {docs.map((d: any) => <div key={d.document_id || d.id} className='card'><h3>{d.title}</h3><p>{d.case_number}</p><div className='form-row'><Link to={`/documents/${d.document_id || d.id}`} className='button'>Открыть</Link>{isAuthenticated && <button type='button' className='button button-secondary' onClick={()=>addFavorite(d.document_id || d.id)}>В избранное</button>}</div></div>)}
  {isStaff(roles) && <div className='card'><Link to='/staff/cases/create'>Создать дело</Link></div>}
  </AppLayout>;
}
