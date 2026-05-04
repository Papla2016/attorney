import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { staffCases } from '../../api/casesApi';
import AppLayout from '../../components/layout/AppLayout';

export default function StaffCasesPage() {
  const { data, error } = useQuery({ queryKey: ['staffCases'], queryFn: async () => (await staffCases()).data, retry: false });
  const items = data?.items || data || [];
  return <AppLayout><h1>Мои дела</h1><Link to='/staff/cases/create' className='button'>Создать дело</Link>{(error as any)?.response?.status===404 && <p className='warning-message'>Backend пока не возвращает список дел работника суда.</p>}{items.map((c:any)=><div className='card' key={c.id}><h3>{c.case_number}</h3><p>{c.status}</p><p>{c.court_name||c.court}</p><p>{c.region}</p><p>{c.document_date}</p><div className='form-row'><Link to={`/staff/cases/${c.id}`}>Открыть</Link><Link to={`/staff/cases/${c.id}/upload`}>Загрузить документ</Link></div></div>)}</AppLayout>;
}
