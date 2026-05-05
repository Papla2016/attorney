import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import AppLayout from '../components/layout/AppLayout';
import { getFavorites, removeFavorite } from '../api/casesApi';
import ServerState from '../components/ui/ServerState';

export default function FavoritesPage(){
  const qc = useQueryClient();
  const { data, isLoading, error } = useQuery({ queryKey:['favorites'], queryFn: async()=> (await getFavorites()).data, retry:false });
  const docs = data?.items || data || [];
  return <AppLayout><h1>Избранные документы</h1><ServerState loading={isLoading} error={error?.message==='Network Error' ? {message:'Network Error'} : error} />
  {(error as any)?.message==='Network Error' && <p className='error-message'>Сервер недоступен. Не удалось загрузить избранное.</p>}
  {!isLoading && !error && docs.length===0 && <p>У вас пока нет избранных документов.</p>}
  {docs.map((d:any)=><div className='card' key={d.document_id || d.id}><h3>{d.title}</h3><p>{d.case_number}</p><p>{d.document_number}</p><p>{d.court_name||d.court}</p><p>{d.region}</p><p>{d.document_date}</p><p>{d.act_type}</p><p>{d.instance}</p><p>{d.legal_article || d.law_article}</p><div className='form-row'><Link className='button' to={`/documents/${d.document_id || d.id}`}>Открыть</Link><button className='button button-secondary' onClick={async()=>{await removeFavorite(d.document_id || d.id); qc.invalidateQueries({queryKey:['favorites']});}}>Удалить из избранного</button></div></div>)}
  </AppLayout>;
}
