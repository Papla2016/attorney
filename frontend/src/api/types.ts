export type Role = 'REGISTERED_USER' | 'COURT_STAFF' | 'JUDGE' | 'COURT_CLERK' | 'ADMIN';
export interface User { id: string; username: string; email?: string; roles: Role[]; }
export interface Court { id: string; name: string; region: string; }
export interface Case { id: string; case_number: string; court?: string; region?: string; status?: string; can_view_restored?: boolean; }
export interface CaseDocument { id: string; title: string; document_number?: string; act_type: string; instance?: string; status?: string; }
export interface PublicDocumentListItem { id: string; title: string; case_number?: string; document_number?: string; court?: string; region?: string; document_date?: string; act_type?: string; instance?: string; law_article?: string; practice_topic?: string; }
export interface PublicDocumentDetails extends PublicDocumentListItem { anonymized_text: string; can_view_restored?: boolean; }
export type FavoriteDocument = PublicDocumentListItem;
export interface EntityMapping { placeholder: string; original_value: string; entity_type: string; }
export interface RestoredDocument { id: string; title: string; original_text: string; anonymized_text: string; entity_mappings: EntityMapping[]; }
export interface RestoredCase { id: string; case_number: string; court?: string; region?: string; documents: RestoredDocument[]; }
export interface CreateCaseRequest { court_id?: string; case_number: string; document_number?: string; document_date?: string; instance?: string; region?: string; law_article?: string; practice_topic?: string; judges?: string[]; staff_ids?: string[]; }
export interface UploadDocumentRequest { title: string; act_type: string; text: string; }
export interface PaginatedResponse<T> { items: T[]; total: number; page: number; page_size: number; }
export interface ApiError { error: { code: string; message: string; details?: Record<string, unknown> }; }
