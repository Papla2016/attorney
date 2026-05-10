import { useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import AppLayout from '../components/layout/AppLayout';
import ServerState from '../components/ui/ServerState';
import CourtDocumentView from '../components/documents/CourtDocumentView';
import { getPublicDocument } from '../api/casesApi';

const getDocumentText = (data: any) =>
  data?.anonymized_text ||
  data?.text ||
  data?.content ||
  data?.public_text ||
  data?.document?.anonymized_text ||
  data?.document?.text ||
  data?.document?.content ||
  data?.document?.public_text ||
  '';

const getDocumentTitle = (data: any) => data?.title || data?.document?.title || 'Судебный документ';

export default function PublicDocumentPage() {
  const { documentId = '' } = useParams();
  const [copied, setCopied] = useState(false);
  const { data, error, isLoading } = useQuery({
    queryKey: ['publicDocument', documentId],
    queryFn: async () => (await getPublicDocument(documentId)).data,
    retry: false,
  });
  const status = (error as any)?.response?.status;
  const documentData = data?.document || data;
  const text = getDocumentText(data);
  const title = getDocumentTitle(data);
  const caseInfo = useMemo(() => ({
    case_number: data?.case_number || documentData?.case_number,
    document_number: data?.document_number || documentData?.document_number,
    court_name: data?.court_name || data?.court || documentData?.court_name || documentData?.court,
    region: data?.region || documentData?.region,
    document_date: data?.document_date || documentData?.document_date || documentData?.date,
    legal_article: data?.legal_article || data?.law_article || documentData?.legal_article || documentData?.law_article,
    judge_names: data?.judge_names || documentData?.judge_names || documentData?.judges,
  }), [data, documentData]);

  const copy = async () => {
    if (!text) return;
    await navigator.clipboard.writeText(text);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 2500);
  };

  const serverUnavailable = [500, 502, 503, 504].includes(status);

  return (
    <AppLayout>
      <div className="case-actions public-document-actions">
        <Link className="button button-secondary" to="/">Назад к поиску</Link>
        <button type="button" onClick={copy} disabled={!text}>{copied ? 'Текст скопирован' : 'Скопировать текст'}</button>
      </div>

      <ServerState loading={isLoading} error={status === 404 || serverUnavailable ? null : error} />
      {status === 404 && <p className="error-message">Документ не найден или не опубликован</p>}
      {serverUnavailable && <p className="error-message">Сервер недоступен. Не удалось загрузить документ.</p>}

      {!isLoading && !error && (
        <>
          {!text && (
            <p className="status-warning">
              Текст документа отсутствует. Возможно, документ ещё не был обезличен или опубликован.
            </p>
          )}
          <CourtDocumentView title={title} text={text} caseInfo={caseInfo} />
        </>
      )}
    </AppLayout>
  );
}
