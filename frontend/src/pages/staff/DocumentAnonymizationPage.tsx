import { Link, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import AppLayout from '../../components/layout/AppLayout';
import ServerState from '../../components/ui/ServerState';
import { getDocumentAnonymization } from '../../api/casesApi';
import AnonymizationWorkspace from '../../components/anonymization/AnonymizationWorkspace';

export default function DocumentAnonymizationPage() {
  const { documentId = '' } = useParams();
  const { data, error, isLoading, refetch } = useQuery({ queryKey: ['documentAnonymization', documentId], queryFn: async () => (await getDocumentAnonymization(documentId)).data, retry: false });
  const caseId = data?.case_id || data?.case?.id || data?.document?.case_id;
  return <AppLayout>
    <div className='case-actions'><h1>Ручная проверка обезличивания</h1>{caseId && <Link className='button button-secondary' to={`/staff/cases/${caseId}`}>Назад к делу</Link>}</div>
    <ServerState loading={isLoading} error={error} />
    {!isLoading && !error && <AnonymizationWorkspace key={documentId} documentId={documentId} caseId={caseId} initialData={data} onSaved={() => refetch()} />}
  </AppLayout>;
}
