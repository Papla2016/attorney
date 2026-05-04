import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { addFavorite, searchPublicDocuments } from '../api/casesApi';
import { Link } from 'react-router-dom';
import AppLayout from '../components/layout/AppLayout';
import { useAuth } from '../auth/useAuth';
import { isStaff } from '../utils/roles';

export default function PublicSearchPage() {
  const [params, setParams] = useState<any>({});
  const { isAuthenticated, roles } = useAuth();
  const { data } = useQuery({ queryKey: ['publicDocs', params], queryFn: async () => (await searchPublicDocuments(params)).data, retry: false });
  const docs = data?.items || data || [];
  return <AppLayout><section className='hero'><h1>Поиск судебных документов</h1><p>Публичный доступ предоставляется только к обезличенным судебным актам. Восстановленные данные доступны только участникам дела и уполномоченным работникам суда.</p></section>
  <div className='card form-card'><form onSubmit={(e:any)=>{e.preventDefault(); const f=new FormData(e.currentTarget); setParams(Object.fromEntries(f.entries()));}}>
  <label>Поиск по номеру дела, статье, суду или тексту</label><div className='form-row'><input name='q'/><button className='button'>Найти</button><button type='button' className='button button-secondary' onClick={()=>setParams({})}>Сбросить</button></div>
  <div className='form-grid'><input name='region' placeholder='регион'/><input name='court_name' placeholder='суд'/><input name='act_type' placeholder='тип судебного акта'/><input name='instance' placeholder='инстанция'/><input name='legal_article' placeholder='статья закона'/><input name='date_from' type='date'/><input name='date_to' type='date'/></div>
  </form></div>
  {isStaff(roles) && <div className='card'><h3>Быстрые действия</h3><div className='form-row'><Link to='/staff/cases/create'>Создать дело</Link><Link to='/staff/cases'>Мои дела</Link><Link to='/staff'>Панель работника суда</Link></div></div>}
  <div className='info-grid'>{['Публичный доступ|Доступны только обезличенные судебные акты','Избранное|Авторизованные пользователи могут сохранять документы','Восстановленные данные|Доступны только участникам дела и работникам суда','Работникам суда|Создание дел, загрузка документов и публикация обезличенных актов'].map((i)=><div className='card' key={i}><h4>{i.split('|')[0]}</h4><p>{i.split('|')[1]}</p></div>)}</div>
  {docs.map((d: any) => <div key={d.document_id} className='card'><h3>{d.title}</h3><p>{d.case_number}</p><p>{d.document_number}</p><p>{d.court_name}</p><p>{d.region}</p><p>{d.document_date}</p><p>{d.act_type}</p><p>{d.instance}</p><p>{d.legal_article}</p><p>{d.judicial_practice}</p><div className='form-row'><Link to={`/documents/${d.document_id}`} className='button'>Открыть</Link>{isAuthenticated && <button type='button' className='button button-secondary' onClick={()=>addFavorite(d.document_id)}>В избранное</button>}</div></div>)}
  </AppLayout>;
}
