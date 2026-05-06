import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { createCase } from '../../api/casesApi';
import AppLayout from '../../components/layout/AppLayout';
import { INSTANCE_OPTIONS } from '../../constants/instances';
import { RUSSIAN_REGIONS } from '../../constants/regions';
import AutocompleteInput from '../../components/ui/AutocompleteInput';
import { LEGAL_ARTICLE_OPTIONS } from '../../constants/legalArticles';

const getCreateCaseError = (error: any) => {
  const status = error?.response?.status;
  if ([400, 422].includes(status)) return 'Проверьте заполнение обязательных полей дела.';
  if ([500, 502, 503, 504].includes(status)) return 'Сервер недоступен или произошла внутренняя ошибка.';
  if (error?.message === 'Network Error' || !error?.response) return 'Сервер недоступен.';
  return 'Не удалось создать дело.';
};

export default function CreateCasePage() {
  const [message, setMessage] = useState('');
  const [errorMessage, setErrorMessage] = useState('');
  const [loading, setLoading] = useState(false);
  const [legalArticle, setLegalArticle] = useState('');
  const nav = useNavigate();

  const onSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setErrorMessage('');
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
      judge_names: String(f.get('judge_names') || '')
        .split(',')
        .map((x) => x.trim())
        .filter(Boolean),
      staff_user_ids: []
    };

    try {
      const res = await createCase(payload);
      const caseId = res.data?.id || res.data?.case_id;
      setMessage('Дело создано');
      if (caseId) nav(`/staff/cases/${caseId}`);
    } catch (er: any) {
      setErrorMessage(getCreateCaseError(er));
    } finally {
      setLoading(false);
    }
  };

  return (
    <AppLayout>
      <div className='card form-card'>
        <h1>Создание дела</h1>
        {message && <p className='success-message'>{message}</p>}
        {errorMessage && <p className='error-message'>{errorMessage}</p>}
        <form onSubmit={onSubmit}>
          <label>ID суда</label><input name='court_id' />
          <label>Номер дела</label><input required name='case_number' />
          <label>Номер документа</label><input name='document_number' />
          <label>Дата документа</label><input type='date' name='document_date' />
          <label>Инстанция</label><select name='instance'>{INSTANCE_OPTIONS.filter(i => i.value).map(i => <option value={i.value} key={i.value}>{i.label}</option>)}</select>
          <label>Регион</label><select required name='region'><option value=''>Выберите регион</option>{RUSSIAN_REGIONS.map(r => <option key={r} value={r}>{r}</option>)}</select>
          <label>Статья закона</label><AutocompleteInput name='legal_article' value={legalArticle} onChange={setLegalArticle} options={LEGAL_ARTICLE_OPTIONS} />
          <label>Судебная практика</label><input name='judicial_practice' />
          <label>Судьи дела</label><input name='judge_names' placeholder='через запятую' />
          <button className='button' disabled={loading}>{loading ? 'Создание...' : 'Создать дело'}</button>
        </form>
      </div>
    </AppLayout>
  );
}
