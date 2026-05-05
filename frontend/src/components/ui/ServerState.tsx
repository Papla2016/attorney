import LoadingSpinner from './LoadingSpinner';

export default function ServerState({ loading, error }: { loading: boolean; error?: any }) {
  if (loading) return <div className='server-state'><LoadingSpinner /><span>Загрузка...</span></div>;
  if (!error) return null;
  const status = error?.response?.status;
  if (error?.message === 'Network Error') return <p className='error-message'>Сервер недоступен</p>;
  if (status === 401) return <p className='error-message'>Необходимо войти в систему</p>;
  if (status === 403) return <p className='error-message'>Недостаточно прав</p>;
  if (status === 404) return <p className='error-message'>Данные не найдены</p>;
  if (status >= 500) return <p className='error-message'>Внутренняя ошибка сервера. Попробуйте позже.</p>;
  return <p className='error-message'>Сервер недоступен</p>;
}
