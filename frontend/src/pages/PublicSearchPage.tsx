import { useQuery } from '@tanstack/react-query';
import { searchPublicDocuments } from '../api/casesApi';
import { Link } from 'react-router-dom';
export default function PublicSearchPage(){
  const {data} = useQuery({queryKey:['publicDocs'], queryFn: async()=> (await searchPublicDocuments({})).data, retry:false});
  const docs = data?.items || data || [];
  return <div><h1>Поиск судебных документов</h1><p>Публичный доступ предоставляется только к обезличенным судебным актам</p>{docs.map((d:any)=><div key={d.id} className='card'><h3>{d.title}</h3><p>{d.case_number}</p><Link to={`/documents/${d.id}`}>Открыть</Link></div>)}</div>;
}
