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
  const [message, setMessage] = useState('');
  const [error, setError] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [legalArticle, setLegalArticle] = useState('');
  const nav = useNavigate();

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    setMessage('');
    setLoading(true);
    const f = new FormData(e.currentTarget);
    const payload = {
      court_id: String(f.get('court_id') || ''),
      case_number: String(f.get('case_number') || ''),
      document_number: String(f.get('document_number') || ''),
      document_date: String(f.get('document_date') || ''),
      instance: String(f.get('instance') || ''),
      region: String(f.get('region') || ''),
      legal_article: String(f.get('legal_article') || ''),
      judicial_practice: String(f.get('judicial_practice') || ''),
      judge_names: String(f.get('judge_names') || '').split(',').map((x) => x.trim()).filter(Boolean),
      staff_user_ids: [],
    };
    try {
      const res = await createCase(payload as any);
      setMessage('Дело создано');
      nav(`/staff/cases/${res.data?.id || ''}`);
    } catch (er: any) {
      setError(er);
      const status = er?.response?.status;
      if (status === 400 || status === 422) setMessage('Проверьте заполнение обязательных полей дела.');
      else if (!er?.response) setMessage(getApiErrorMessage(er));
    } finally {
      setLoading(false);
    }
  }

  return (
    <AppLayout>
      <div className='card form-card'>
        <h1>Создание дела</h1>
        {message && <p className={error ? 'error-message' : 'success-message'}>{message}</p>}
        <ServerState loading={loading} error={error}/>
        <form onSubmit={handleSubmit}>
          <label>ID суда</label><input name='court_id' placeholder='Можно оставить пустым для временного дела'/>
          <label>Номер дела</label><input required name='case_number'/>
          <label>Номер документа</label><input name='document_number'/>
          <label>Дата документа</label><input type='date' name='document_date'/>
          <label>Инстанция</label><select name='instance'>{INSTANCE_OPTIONS.filter(i=>i.value).map(i=><option value={i.value} key={i.value}>{i.label}</option>)}</select>
          <label>Регион</label><select required name='region'><option value=''>Выберите регион</option>{RUSSIAN_REGIONS.map(r=><option key={r} value={r}>{r}</option>)}</select>
          <label>Статья закона</label><AutocompleteInput name='legal_article' value={legalArticle} onChange={setLegalArticle} options={LEGAL_ARTICLE_OPTIONS} />
          <label>Судебная практика</label><input name='judicial_practice'/>
          <label>Судьи дела</label><input name='judge_names' placeholder='через запятую'/>
          <button className='button' disabled={loading}>Создать дело</button>
        </form>
      </div>
    </AppLayout>
  );
}
