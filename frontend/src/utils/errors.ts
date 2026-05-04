export const getApiErrorMessage = (error: any, context?: 'login'): string => {
  const status = error?.response?.status;

  if (context === 'login' && status === 401) return 'Неверный логин или пароль';
  if (status === 401) return 'Сессия истекла. Войдите снова.';
  if (status === 403) return 'Недостаточно прав';
  if (status === 404) return 'Данные не найдены';
  if ([500, 502, 503, 504].includes(status)) return 'Внутренняя ошибка сервера. Попробуйте позже.';
  if (error?.message === 'Network Error') return 'Не удалось подключиться к серверу';

  return 'Не удалось выполнить действие';
};
