import { client } from './client';

export type CourtPayload = {
  name: string;
  court_type: string;
  region: string;
  address: string;
};

export type AuditLogParams = {
  action?: string;
  user?: string;
  resource_type?: string;
  date_from?: string;
  date_to?: string;
};

export const getCourts = () => client.get('/cases/admin/courts');
export const createCourt = (payload: CourtPayload) => client.post('/cases/admin/courts', payload);
export const updateCourt = (courtId: string, payload: Partial<CourtPayload>) => client.patch(`/cases/admin/courts/${courtId}`, payload);
export const deleteCourt = (courtId: string) => client.delete(`/cases/admin/courts/${courtId}`);
export const getAuditLog = (params?: AuditLogParams) => client.get('/cases/admin/audit', { params });
export const getSystemHealth = () => client.get('/cases/admin/system-health');
