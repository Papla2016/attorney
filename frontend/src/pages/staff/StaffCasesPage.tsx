import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { staffCases } from '../../api/casesApi';
import AppLayout from '../../components/layout/AppLayout';
import ServerState from '../../components/ui/ServerState';

export default function StaffCasesPage() {
  const { data, error, isLoading } = useQuery({ queryKey: ['staffCases'], queryFn: async () => (await staffCases()).data, retry: false });
  const items = data?.items || data || [];
  return <AppLayout><h1>Мои дела</h1><Link to='/staff/cases/create' className='button'>Создать дело</Link><ServerState loading={isLoading} error={error} />{(error as any)?.response?.status===404 && <p className='warning-message'>Backend пока не возвращает список дел работника суда.</p>}{items.map((c:any)=><div className='card' key={c.id}><h3>{c.case_number}</h3></div>)}</AppLayout>;
}
