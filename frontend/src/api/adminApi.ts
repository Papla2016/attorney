import { client } from './client';

export const getSystemHealth = () => client.get('/cases/admin/system-health');
export const getCourts = () => client.get('/cases/admin/courts');
export const createCourt = (payload: any) => client.post('/cases/admin/courts', payload);
export const updateCourt = (courtId: string, payload: any) => client.patch(`/cases/admin/courts/${courtId}`, payload);
export const deleteCourt = (courtId: string) => client.delete(`/cases/admin/courts/${courtId}`);
export const getAuditLog = (params?: any) => client.get('/cases/admin/audit', { params });
