export const ENTITY_TYPE_LABELS: Record<string, string> = {
  PERSON_FULL_NAME: 'ФИО',
  CASE_PARTICIPANT: 'Участник дела',
  JUDGE: 'Судья',
  COURT_SECRETARY: 'Секретарь судебного заседания',
  ADDRESS: 'Адрес',
  LOCATION: 'Место',
  ORGANIZATION: 'Организация',
  PHONE: 'Телефон',
  EMAIL: 'Электронная почта',
  PASSPORT: 'Паспортные данные',
  SNILS: 'СНИЛС',
  INN: 'ИНН',
  BIRTH_DATE: 'Дата рождения',
  DATE: 'Дата',
  OTHER: 'Иные данные'
};

export const ENTITY_TYPE_OPTIONS = [
  { value: 'PERSON_FULL_NAME', label: 'ФИО' },
  { value: 'CASE_PARTICIPANT', label: 'Участник дела' },
  { value: 'JUDGE', label: 'Судья' },
  { value: 'COURT_SECRETARY', label: 'Секретарь судебного заседания' },
  { value: 'ADDRESS', label: 'Адрес' },
  { value: 'LOCATION', label: 'Место' },
  { value: 'ORGANIZATION', label: 'Организация' },
  { value: 'PHONE', label: 'Телефон' },
  { value: 'EMAIL', label: 'Электронная почта' },
  { value: 'PASSPORT', label: 'Паспортные данные' },
  { value: 'SNILS', label: 'СНИЛС' },
  { value: 'INN', label: 'ИНН' },
  { value: 'BIRTH_DATE', label: 'Дата рождения' },
  { value: 'DATE', label: 'Дата' },
  { value: 'OTHER', label: 'Иные данные' }
];

export const SOURCE_LABELS: Record<string, string> = {
  natasha: 'Модель Natasha',
  regex: 'Регулярное выражение',
  rule: 'Правило',
  manual: 'Добавлено вручную',
  unknown: 'Неизвестно'
};

export function getEntityTypeLabel(value?: string) {
  return ENTITY_TYPE_LABELS[value || ''] || value || '—';
}

export function getSourceLabel(value?: string) {
  return SOURCE_LABELS[value || ''] || value || '—';
}
