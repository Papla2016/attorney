export type Role = 'REGISTERED_USER' | 'COURT_STAFF' | 'JUDGE' | 'COURT_CLERK' | 'ADMIN';
export interface User { id: string; username: string; email?: string; role?: Role; roles?: Role[]; }
export interface Court { id: string; name: string; court_type?: string; type?: string; region: string; address?: string; }
export interface Case { id: string; case_number: string; document_number?: string; document_date?: string; court?: string; court_name?: string; region?: string; instance?: string; legal_article?: string; judicial_practice?: string; law_article?: string; practice_topic?: string; status?: string; user_role?: string; role?: string; can_view_restored?: boolean; participants?: any[]; judge_names?: string[]; judges?: string[]; documents?: CaseDocument[]; }
export interface CaseDocument { id: string; title: string; document_number?: string; act_type?: string; document_type?: string; instance?: string; status?: string; anonymized_text?: string; full_text?: string; text?: string; can_view_restored?: boolean; }
export interface PublicDocumentListItem { id: string; title: string; case_number?: string; document_number?: string; court?: string; region?: string; document_date?: string; act_type?: string; instance?: string; law_article?: string; practice_topic?: string; is_favorite?: boolean; favorite?: boolean; }
export interface PublicDocumentDetails extends PublicDocumentListItem { anonymized_text: string; can_view_restored?: boolean; }
export type FavoriteDocument = PublicDocumentListItem;
export type EntityOccurrence = { surface_value: string; start?: number; end?: number; };
export type MergeCandidate = { cluster_id: string; placeholder?: string; normalized_value: string; };
export interface EntityMapping { id?: string; entity_key?: string; cluster_id?: string; placeholder?: string; original_value: string; normalized_value?: string; aliases?: string[]; entity_class?: string; entity_type?: string; person_role?: string; context_kind?: string; role?: string; context?: string; redaction_decision?: 'REDACT' | 'KEEP' | 'REVIEW'; redaction_reason?: string; source?: 'natasha' | 'regex' | 'rule' | 'manual'; detection_method?: string; ambiguity_reason?: string; date_purpose?: string; location_purpose?: string; requires_review?: boolean; review_reason?: string; occurrences_count?: number; occurrences?: EntityOccurrence[]; merge_candidates?: MergeCandidate[]; }
export interface RestoredDocument { id: string; title: string; original_text: string; anonymized_text: string; entity_mappings: EntityMapping[]; }
export interface RestoredCase { id: string; case_number: string; court?: string; region?: string; documents: RestoredDocument[]; }
export interface CreateCaseRequest { court_id?: string; case_number: string; document_number?: string; document_date?: string; instance?: string; region?: string; legal_article?: string; judicial_practice?: string; judge_names?: string[]; staff_user_ids?: string[]; }
export interface UpdateCaseRequest { court_id?: string; court_name?: string; case_number?: string; document_number?: string; document_date?: string; instance?: string; region?: string; legal_article?: string; judicial_practice?: string; judge_names?: string[]; participants?: string[]; }
export interface UploadDocumentRequest { title: string; act_type: string; text?: string; content_format?: 'PLAIN_TEXT' | 'TIPTAP_JSON'; content?: unknown; }
export interface PaginatedResponse<T> { items: T[]; total: number; page: number; page_size: number; }
export interface ApiError { error: { code: string; message: string; details?: Record<string, unknown> }; }

export interface AnonymizationResult {
  document_id: string;
  anonymized_text?: string;
  anonymized_content?: unknown;
  content_format?: 'TIPTAP_JSON' | 'PLAIN_TEXT';
  mappings?: EntityMapping[];
  recognized_but_kept?: EntityMapping[];
  review_entities?: EntityMapping[];
  review_markers?: ReviewMarker[];
  pending_review?: PendingReviewEntity[];
  pending_markers?: PendingMarker[];
  manual_decisions?: unknown[];
  publication_redaction_mode?: 'NORMATIVE' | 'EXTENDED_SAFE';
  ner_provider?: string;
  document_revision?: number;
}


export type PendingReviewEntity = {
  entity_key: string;
  surface_value: string;
  normalized_value?: string;
  entity_class: string;
  person_role?: string;
  start?: number;
  end?: number;
  reason: string;
  suggested_action?: 'REDACT' | 'KEEP';
  merge_candidates?: Array<{ cluster_id: string; placeholder?: string; normalized_value: string; }>;
};

export type PendingMarker = { entity_key: string; surface_value: string; start?: number; end?: number; reason: string; };

export type ReviewMarker = { entity_key?: string; cluster_id?: string; placeholder?: string; display_text?: string; reason: string; occurrences_count?: number; };
