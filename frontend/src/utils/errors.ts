export const getErrorMessage = (error: any): string => {
  if (error?.response?.data?.error?.message) return error.response.data.error.message;
  if (error?.response?.status === 403) return 'Недостаточно прав для выполнения действия.';
  if (error?.response?.status === 404) return 'Запрашиваемые данные не найдены.';
  if (error?.message === 'Network Error') return 'Не удалось подключиться к серверу.';
  return error?.message || 'Произошла ошибка.';
};
