import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import AppLayout from '../../components/layout/AppLayout';
import ServerState from '../../components/ui/ServerState';
import { createCourt, getCourts } from '../../api/adminApi';
import { RUSSIAN_REGIONS } from '../../constants/regions';

const COURT_TYPES = [
  ['MAGISTRATE_COURT', 'Мировой судья'],
  ['DISTRICT_COURT', 'Районный/городской суд'],
  ['REGIONAL_COURT', 'Суд субъекта РФ'],
  ['APPEAL_GENERAL_COURT', 'Апелляционный суд общей юрисдикции'],
  ['CASSATION_GENERAL_COURT', 'Кассационный суд общей юрисдикции'],
  ['SUPREME_COURT_RF', 'Верховный Суд РФ'],
  ['MILITARY_COURT', 'Военный суд'],
  ['OTHER_GENERAL_JURISDICTION', 'Иной суд общей юрисдикции'],
];

export default function CourtsAdminPage() {
  const [message, setMessage] = useState('');
  const { data, error, isLoading, refetch } = useQuery({ queryKey: ['adminCourts'], queryFn: getCourts, retry: false });
  const courts = data?.data?.items || [];

  async function handleCreate(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setMessage('');
    const f = new FormData(e.currentTarget);
    await createCourt({ name: String(f.get('name') || ''), court_type: String(f.get('court_type') || 'DISTRICT_COURT'), region: String(f.get('region') || ''), address: String(f.get('address') || '') });
    e.currentTarget.reset();
    setMessage('Суд добавлен');
    await refetch();
  }

  return (
    <AppLayout>
      <h1>Справочник судов</h1>
      {message && <p className='success-message'>{message}</p>}
      <ServerState loading={isLoading} error={error}/>
      {(error as any)?.response?.status === 404 && <div className='card'>Backend пока не поддерживает справочник судов.</div>}
      <div className='card form-card'>
        <h2>Добавить суд</h2>
        <form onSubmit={handleCreate}>
          <label>Название суда</label><input name='name' required placeholder='Название суда'/>
          <label>Тип суда</label><select name='court_type'>{COURT_TYPES.map(([value,label]) => <option key={value} value={value}>{label}</option>)}</select>
          <label>Регион</label><select name='region' required><option value=''>Выберите регион</option>{RUSSIAN_REGIONS.map(r => <option key={r} value={r}>{r}</option>)}</select>
          <label>Адрес</label><input name='address' placeholder='Адрес суда'/>
          <button className='button'>Добавить суд</button>
        </form>
      </div>
      <div className='card'>
        <h2>Суды</h2>
        <table className='data-table courts-table'>
          <thead><tr><th>Название</th><th>Тип</th><th>Регион</th><th>Адрес</th></tr></thead>
          <tbody>{courts.map((c: any) => <tr key={c.id}><td>{c.name}</td><td>{COURT_TYPES.find(([v]) => v === c.court_type)?.[1] || c.court_type}</td><td>{c.region}</td><td>{c.address}</td></tr>)}</tbody>
        </table>
      </div>
    </AppLayout>
  );
}
