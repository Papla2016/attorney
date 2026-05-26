import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import AppLayout from '../components/layout/AppLayout';
import { getFavorites, removeFavorite } from '../api/casesApi';
import ServerState from '../components/ui/ServerState';

const ACT: Record<string,string> = { DECISION:'Решение', SENTENCE:'Приговор', RULING:'Постановление', DETERMINATION:'Определение', COURT_ORDER:'Судебный приказ' };
const INST: Record<string,string> = { FIRST:'Первая инстанция', APPEAL:'Апелляция', CASSATION:'Кассация', SUPERVISION:'Надзор', REVIEW:'Пересмотр' };
const val = (v:any) => v || '—';
const date = (v?:string) => (v && /^\d{4}-\d{2}-\d{2}$/.test(v) ? `${v.slice(8,10)}.${v.slice(5,7)}.${v.slice(0,4)}` : val(v));

export default function FavoritesPage(){
  const qc = useQueryClient();
  const { data, isLoading, error } = useQuery({ queryKey:['favorites'], queryFn: async()=> (await getFavorites()).data, retry:false });
  const docs = data?.items || data || [];
  return <AppLayout><h1>Избранные документы</h1><ServerState loading={isLoading} error={error?.message==='Network Error' ? {message:'Network Error'} : error} />
  {(error as any)?.message==='Network Error' && <p className='error-message'>Сервер недоступен. Не удалось загрузить избранное.</p>}
  {!isLoading && !error && docs.length===0 && <p>У вас пока нет избранных документов.</p>}
  {docs.map((d:any)=><div className='favorite-document-card' key={d.document_id || d.id}><h3>{val(d.title)}</h3><div className='favorite-document-meta-grid'>
    <p><b>Номер дела:</b> {val(d.case_number)}</p><p><b>Номер документа:</b> {val(d.document_number)}</p><p><b>Суд:</b> {val(d.court_name||d.court)}</p><p><b>Регион:</b> {val(d.region)}</p>
    <p><b>Дата документа:</b> {date(d.document_date)}</p><p><b>Тип судебного акта:</b> {ACT[d.act_type] || val(d.act_type)}</p><p><b>Инстанция:</b> {INST[d.instance] || val(d.instance)}</p><p><b>Статья закона:</b> {val(d.legal_article || d.law_article)}</p>
  </div><div className='form-row'><Link className='button' to={`/documents/${d.document_id || d.id}`}>Открыть документ</Link><button className='button button-secondary' onClick={async()=>{await removeFavorite(d.document_id || d.id); qc.invalidateQueries({queryKey:['favorites']});}}>Удалить из избранного</button></div></div>)}
  </AppLayout>;
}
