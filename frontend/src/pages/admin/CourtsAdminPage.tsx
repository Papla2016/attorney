import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import AppLayout from '../../components/layout/AppLayout';
import { createCourt, deleteCourt, getCourts, updateCourt, type CourtPayload } from '../../api/adminApi';
import ServerState from '../../components/ui/ServerState';
import { RUSSIAN_REGIONS } from '../../constants/regions';

const COURT_TYPES = [
  ['MAGISTRATE_COURT', 'Мировой судья'],
  ['DISTRICT_COURT', 'Районный/городской суд'],
  ['REGIONAL_COURT', 'Суд субъекта РФ'],
  ['APPEAL_GENERAL_COURT', 'Апелляционный суд общей юрисдикции'],
  ['CASSATION_GENERAL_COURT', 'Кассационный суд общей юрисдикции'],
  ['SUPREME_COURT_RF', 'Верховный Суд РФ'],
  ['MILITARY_COURT', 'Военный суд'],
  ['OTHER_GENERAL_JURISDICTION', 'Иной суд общей юрисдикции']
];
const typeLabel = (v: string) => COURT_TYPES.find(([value]) => value === v)?.[1] || v || '—';
const emptyForm: CourtPayload = { name: '', court_type: 'DISTRICT_COURT', region: '', address: '' };

export default function CourtsAdminPage() {
  const qc = useQueryClient();
  const [form, setForm] = useState<CourtPayload>(emptyForm);
  const [editingId, setEditingId] = useState('');
  const [message, setMessage] = useState('');
  const [errorMessage, setErrorMessage] = useState('');
  const { data, error, isLoading } = useQuery({ queryKey: ['adminCourts'], queryFn: async () => (await getCourts()).data, retry: false });
  const courts = data?.items || data || [];
  const notImplemented = (error as any)?.response?.status === 404;

  const setField = (name: keyof CourtPayload, value: string) => setForm((prev) => ({ ...prev, [name]: value }));
  const resetForm = () => { setForm(emptyForm); setEditingId(''); };
  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage('');
    setMessage('');
    try {
      if (editingId) await updateCourt(editingId, form);
      else await createCourt(form);
      setMessage(editingId ? 'Суд обновлён' : 'Суд добавлен');
      resetForm();
      await qc.invalidateQueries({ queryKey: ['adminCourts'] });
    } catch (er: any) {
      if (er?.response?.status === 404) setErrorMessage('Backend пока не поддерживает справочник судов.');
      else setErrorMessage('Не удалось сохранить суд.');
    }
  };

  return (
    <AppLayout>
      <h1>Справочник судов</h1>
      <ServerState loading={isLoading} error={notImplemented ? null : error} />
      {notImplemented && <p className='warning-message'>Backend пока не поддерживает справочник судов.</p>}
      {message && <p className='success-message'>{message}</p>}
      {errorMessage && <p className='error-message'>{errorMessage}</p>}
      {!notImplemented && <>
        <div className='card form-card'>
          <h3>{editingId ? 'Редактировать суд' : 'Добавить суд'}</h3>
          <form onSubmit={onSubmit}>
            <label>Название суда</label><input value={form.name} onChange={(e) => setField('name', e.target.value)} required />
            <label>Тип суда</label><select value={form.court_type} onChange={(e) => setField('court_type', e.target.value)}>{COURT_TYPES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select>
            <label>Регион</label><select name='region' value={form.region} onChange={(e) => setField('region', e.target.value)} required><option value=''>Выберите регион</option>{RUSSIAN_REGIONS.map((region) => <option key={region} value={region}>{region}</option>)}</select>
            <label>Адрес</label><input value={form.address} onChange={(e) => setField('address', e.target.value)} />
            <div className='form-row'><button className='button'>{editingId ? 'Сохранить изменения' : 'Добавить суд'}</button>{editingId && <button type='button' className='button button-secondary' onClick={resetForm}>Отмена</button>}</div>
          </form>
        </div>
        <div className='card table-card'>
          <table className='courts-table'><thead><tr><th>Название</th><th>Тип суда</th><th>Регион</th><th>Адрес</th><th>Действия</th></tr></thead><tbody>
            {courts.map((court: any) => <tr key={court.id || court.court_id}><td>{court.name}</td><td>{typeLabel(court.court_type || court.type)}</td><td>{court.region}</td><td>{court.address || '—'}</td><td><div className='form-row'><button className='button button-secondary' onClick={() => { setEditingId(court.id || court.court_id); setForm({ name: court.name || '', court_type: court.court_type || court.type || 'DISTRICT_COURT', region: court.region || '', address: court.address || '' }); }}>Редактировать</button><button className='button button-danger' onClick={async () => { await deleteCourt(court.id || court.court_id); await qc.invalidateQueries({ queryKey: ['adminCourts'] }); }}>Удалить</button></div></td></tr>)}
            {!isLoading && courts.length === 0 && <tr><td colSpan={5}>Суды пока не добавлены.</td></tr>}
          </tbody></table>
        </div>
      </>}
    </AppLayout>
  );
}
