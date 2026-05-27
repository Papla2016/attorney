import { client } from './client';
import type { AnonymizationResult, CreateCaseRequest, UploadDocumentRequest, UpdateCaseRequest, EntityMapping } from './types';

export const searchPublicDocuments = (params: any) => client.get('/cases/public/documents', { params });
export const getPublicDocument = (id: string) => client.get(`/cases/public/documents/${id}`);
export const getFavorites = () => client.get('/cases/me/favorites');
export const addFavorite = (documentId: string) => client.post(`/cases/me/favorites/${documentId}`);
export const removeFavorite = (documentId: string) => client.delete(`/cases/me/favorites/${documentId}`);
export const participatingCases = () => client.get('/cases/me/participating');
export const restoredCase = (caseId: string) => client.get(`/cases/${caseId}/restored`);
export const createCase = (payload: CreateCaseRequest) => client.post('/cases', payload);
export const updateCase = (caseId: string, payload: UpdateCaseRequest) => client.patch(`/cases/${caseId}`, payload);
export const staffCases = () => client.get('/cases/staff/my');
export const caseDetails = (caseId: string) => client.get(`/cases/${caseId}`);
export const uploadDoc = (caseId: string, payload: UploadDocumentRequest) => client.post(`/cases/${caseId}/documents`, payload);
export const docStatus = (docId: string) => client.get(`/cases/documents/${docId}/status`);
export const publishDocument = (docId: string) => client.post(`/cases/documents/${docId}/publish`);
export const updateCaseStatus = (caseId: string, status: 'DRAFT' | 'PUBLISHED' | 'ARCHIVED') => client.patch(`/cases/${caseId}/status`, { status });
export const getDocumentAnonymization = (documentId: string) => client.get(`/cases/documents/${documentId}/anonymization`);
export const addDocumentMapping = (documentId: string, payload: { original_value: string; entity_type: string; mode: 'new' | 'existing'; placeholder?: string }) => client.post(`/cases/documents/${documentId}/mappings`, payload);

export const updateDocumentMapping = (documentId: string, mappingId: string, payload: { placeholder: string; original_value: string; entity_type: string }) => client.patch(`/cases/documents/${documentId}/mappings/${mappingId}`, payload);
export const deleteDocumentMapping = (documentId: string, mappingId: string) => client.delete(`/cases/documents/${documentId}/mappings/${mappingId}`);

export const mergeDocumentEntities = (documentId: string, payload: { target_entity_id: string; source_entity_ids: string[] }) => client.post(`/cases/documents/${documentId}/entities/merge`, payload);
export const splitEntityMention = (documentId: string, entityId: string, mentionId: string) => client.post(`/cases/documents/${documentId}/entities/${entityId}/mentions/${mentionId}/split`);

export const mergeDocumentMappings = (documentId: string, payload: { target_mapping_id: string; source_mapping_ids: string[] }) => client.post(`/cases/documents/${documentId}/mappings/merge`, payload);
export const reanonymizeDocument = (documentId: string, payload: { mappings: EntityMapping[]; publication_redaction_mode: 'NORMATIVE' | 'EXTENDED_SAFE' }) => client.post<AnonymizationResult>(`/cases/documents/${documentId}/reanonymize`, payload);
export const saveAnonymization = (documentId: string, payload: { anonymized_text: string; anonymized_content?: unknown; content_format?: 'TIPTAP_JSON'; mappings: EntityMapping[] }) => client.post<AnonymizationResult>(`/cases/documents/${documentId}/save-anonymization`, payload);
export const deleteCaseDocument = (caseId: string, documentId: string) => client.delete(`/cases/${caseId}/documents/${documentId}`);

export const repairPlaceholders = (documentId: string) => client.post(`/cases/documents/${documentId}/mappings/repair-placeholders`);

export const applyRedactionDecision = (
  documentId: string,
  payload: {
    entity_key?: string;
    selected_text: string;
    decision: 'REDACT' | 'KEEP' | 'MERGE_WITH_EXISTING';
    entity_class: string;
    person_role?: string;
    target_cluster_id?: string;
    reason?: string;
  }
) => client.post<AnonymizationResult>(`/cases/documents/${documentId}/redaction-decisions`, payload);


export const scanEditedDraft = (
  documentId: string,
  payload: { text: string; content: unknown; content_format: 'TIPTAP_JSON'; document_revision: number }
) => client.post<AnonymizationResult>(`/cases/documents/${documentId}/draft-scan`, payload);
