export const formatDate = (v?: string) => (v ? new Date(v).toLocaleDateString('ru-RU') : '—');
