export const ENTITY_TYPE_LABELS: Record<string, string> = {
  PERSON_FULL_NAME: 'ФИО',
  CASE_PARTICIPANT: 'Участник дела',
  JUDGE: 'Судья',
  COURT_SECRETARY: 'Секретарь судебного заседания',
  ADDRESS: 'Адрес',
  LOCATION: 'Место',
  PLACE: 'Место',
  ORGANIZATION: 'Организация',
  PHONE: 'Телефон',
  EMAIL: 'Электронная почта',
  PASSPORT: 'Паспортные данные',
  SNILS: 'СНИЛС',
  INN: 'ИНН',
  BIRTH_DATE: 'Дата рождения',
  DATE: 'Дата',
  CADASTRAL_NUMBER: 'Кадастровый номер',
  PROPERTY_IDENTIFIER: 'Кадастровый номер',
  PERSON: 'ФИО',
  OTHER: 'Другие сведения'
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


export const PERSON_ROLE_LABELS: Record<string, string> = {
  JUDGE: 'Судья', COURT_SECRETARY: 'Секретарь судебного заседания', PLAINTIFF: 'Истец', DEFENDANT: 'Ответчик', THIRD_PARTY: 'Третье лицо', REPRESENTATIVE: 'Представитель', WITNESS: 'Свидетель', PROSECUTOR: 'Прокурор', ADVOCATE: 'Адвокат', CONVICTED: 'Осуждённый', ACQUITTED: 'Оправданный', ADMINISTRATIVE_OFFENDER: 'Лицо, привлекаемое к административной ответственности', OTHER_PERSON: 'Иное лицо', UNKNOWN: 'Роль не определена'
};
export const REDACTION_DECISION_LABELS: Record<string, string> = { REDACT: 'Обезличить', KEEP: 'Оставить в тексте', REVIEW: 'Требуется проверка' };
export const DATE_PURPOSE_LABELS: Record<string, string> = { BIRTH_DATE: 'Дата рождения', DOCUMENT_DATE: 'Дата документа', HEARING_DATE: 'Дата судебного заседания', CONTRACT_DATE: 'Дата договора', EVENT_DATE: 'Дата события', UNKNOWN_DATE: 'Назначение даты не определено' };
export const LOCATION_PURPOSE_LABELS: Record<string, string> = { RESIDENCE_ADDRESS: 'Адрес проживания', STAY_ADDRESS: 'Адрес пребывания', BIRTH_PLACE: 'Место рождения', PROPERTY_LOCATION: 'Местонахождение имущества', VEHICLE_LOCATION: 'Местонахождение транспортного средства', COURT_LOCATION: 'Местонахождение суда', ORGANIZATION_LOCATION: 'Адрес организации', GENERIC_LOCATION: 'Место', UNKNOWN_LOCATION: 'Назначение места не определено' };
