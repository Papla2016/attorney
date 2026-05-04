import { client } from './client';
export const listCourts = () => client.get('/cases/dictionaries/courts');
