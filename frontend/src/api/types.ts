export type Role = 'REGISTERED_USER' | 'COURT_STAFF' | 'JUDGE' | 'COURT_CLERK' | 'ADMIN';
export interface User { id: string; username: string; email?: string; role?: Role; roles?: Role[]; }
export interface Court { id: string; name: string; court_type?: string; type?: string; region: string; address?: string; }
export interface Case { id: string; case_number: string; document_number?: string; document_date?: string; court?: string; court_name?: string; region?: string; instance?: string; legal_article?: string; judicial_practice?: string; law_article?: string; practice_topic?: string; status?: string; user_role?: string; role?: string; can_view_restored?: boolean; participants?: any[]; judge_names?: string[]; judges?: string[]; documents?: CaseDocument[]; }
export interface CaseDocument { id: string; title: string; document_number?: string; act_type?: string; document_type?: string; instance?: string; status?: string; anonymized_text?: string; full_text?: string; text?: string; can_view_restored?: boolean; }
export interface PublicDocumentListItem { id: string; title: string; case_number?: string; document_number?: string; court?: string; region?: string; document_date?: string; act_type?: string; instance?: string; law_article?: string; practice_topic?: string; is_favorite?: boolean; favorite?: boolean; }
export interface PublicDocumentDetails extends PublicDocumentListItem { anonymized_text: string; can_view_restored?: boolean; }
export type FavoriteDocument = PublicDocumentListItem;
export interface EntityMapping { placeholder: string; original_value: string; entity_type: string; source?: string; }
export interface RestoredDocument { id: string; title: string; original_text: string; anonymized_text: string; entity_mappings: EntityMapping[]; }
export interface RestoredCase { id: string; case_number: string; court?: string; region?: string; documents: RestoredDocument[]; }
export interface CreateCaseRequest { court_id?: string; case_number: string; document_number?: string; document_date?: string; instance?: string; region?: string; legal_article?: string; judicial_practice?: string; judge_names?: string[]; staff_user_ids?: string[]; }
export interface UpdateCaseRequest { court_id?: string; court_name?: string; case_number?: string; document_number?: string; document_date?: string; instance?: string; region?: string; legal_article?: string; judicial_practice?: string; judge_names?: string[]; participants?: string[]; }
export interface UploadDocumentRequest { title: string; act_type: string; text: string; }
export interface PaginatedResponse<T> { items: T[]; total: number; page: number; page_size: number; }
export interface ApiError { error: { code: string; message: string; details?: Record<string, unknown> }; }
