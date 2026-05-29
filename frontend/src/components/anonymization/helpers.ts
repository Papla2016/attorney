import type { EntityMapping, RedactionEntity } from '../../api/types';

type SelectableEntityText = { original_value?: string; canonical_value?: string; normalized_value?: string; mentions?: Array<{ surface_value?: string }> };

export const selectedTextForEntity = (entity: SelectableEntityText) =>
  entity.original_value || entity.canonical_value || entity.normalized_value || entity.mentions?.[0]?.surface_value || '';

export const legacyMappingToEntity = (m: EntityMapping, index: number, decision: 'REDACT' | 'KEEP' = 'REDACT'): RedactionEntity => ({
  entity_id: m.id || m.cluster_id || m.entity_key || `legacy-${index}`,
  entity_key: m.entity_key,
  placeholder: m.placeholder,
  entity_class: m.entity_class || m.entity_type || 'OTHER',
  canonical_value: m.normalized_value || m.original_value,
  normalized_value: m.normalized_value,
  person_role: m.person_role || m.role,
  context_label: m.context || m.context_kind,
  context_kind: m.context_kind,
  redaction_decision: decision,
  requires_review: m.requires_review,
  review_reason: m.review_reason || m.ambiguity_reason,
  source: m.source,
  mentions_count: m.occurrences_count || m.occurrences?.length || 1,
  mentions: (m.occurrences?.length ? m.occurrences : [{ surface_value: m.original_value }]).map((occ, i) => ({
    mention_id: `${m.id || m.cluster_id || m.entity_key || index}-${i}`,
    entity_id: m.id || m.cluster_id || m.entity_key || `legacy-${index}`,
    surface_value: occ.surface_value,
    normalized_value: m.normalized_value,
    start: occ.start,
    end: occ.end,
    replacement_value: m.placeholder,
    format: 'OTHER',
  })),
  merge_candidates: m.merge_candidates,
});

export const getEntityKey = (entity: RedactionEntity) => entity.entity_key || entity.entity_id;

export const formatMentionFormat = (format?: string) => {
  if (format === 'FULL') return 'полное ФИО';
  if (format === 'INITIALS') return 'инициалы';
  return 'другое';
};

export const getApiErrorMessage = (err: unknown) => {
  const anyErr = err as any;
  const data = anyErr?.response?.data || {};
  const error = data.error || data.detail?.error;
  const code = error?.code || data.code;
  const backendMessage = error?.message || data.message || data.detail?.message;
  const messages: Record<string, string> = {
    PENDING_REVIEW_REQUIRED: 'Перед повторным обезличиванием обработайте найденные в изменённом тексте фрагменты.',
    CROSS_TEXT_NODE_MENTION_UNSUPPORTED: 'Найденное значение пересекает разные участки форматирования. Уберите частичное форматирование этого значения или обработайте его вручную.',
    KEEP_REQUIRES_STRUCTURED_CONTENT: 'Чтобы оставить значение в тексте, сохраните документ в структурированном формате редактора.',
    MERGE_ENTITIES_MARK_NOT_FOUND: 'Не удалось найти отметку объединяемой сущности в документе. Обновите рабочую версию и повторите действие.',
    PLACEHOLDER_MANAGED_AUTOMATICALLY: 'Условное обозначение формируется системой и не редактируется вручную.',
  };
  return (code && messages[code]) || backendMessage || 'Операция не выполнена. Попробуйте ещё раз.';
};

export const mergeCandidateLabel = (candidate: { placeholder?: string; canonical_value?: string; normalized_value?: string; entity_id?: string; cluster_id?: string; entity_class?: string }) => {
  const value = candidate.canonical_value || candidate.normalized_value || 'без значения';
  return candidate.placeholder ? `${candidate.placeholder} — ${value}` : value;
};
