export type CourtDocumentCaseInfo = {
  case_number?: string;
  document_number?: string;
  court_name?: string;
  region?: string;
  document_date?: string;
  legal_article?: string;
  judge_names?: string[];
};

type CourtDocumentViewProps = {
  title?: string;
  text?: string;
  caseInfo?: CourtDocumentCaseInfo;
  isRestored?: boolean;
  caseData?: any;
  document?: any;
  restored?: boolean;
};

const firstText = (...values: any[]) => values.find((value) => typeof value === 'string' && value.trim()) || '';
const list = (value: any) => (Array.isArray(value) ? value.filter(Boolean) : []);
const join = (items?: string[]) => (items?.filter(Boolean).length ? items.filter(Boolean).join(', ') : '—');

export default function CourtDocumentView({
  title,
  text,
  caseInfo,
  isRestored,
  caseData,
  document,
  restored,
}: CourtDocumentViewProps) {
  const info: CourtDocumentCaseInfo = {
    case_number: caseInfo?.case_number || caseData?.case_number || document?.case_number,
    document_number: caseInfo?.document_number || caseData?.document_number || document?.document_number,
    court_name: caseInfo?.court_name || caseData?.court_name || caseData?.court || document?.court_name || document?.court,
    region: caseInfo?.region || caseData?.region || document?.region,
    document_date: caseInfo?.document_date || caseData?.document_date || document?.document_date || document?.date,
    legal_article: caseInfo?.legal_article || caseData?.legal_article || caseData?.law_article || document?.legal_article || document?.law_article,
    judge_names: caseInfo?.judge_names || list(caseData?.judge_names || caseData?.judges || document?.judge_names || document?.judges),
  };
  const documentTitle = firstText(title, document?.title, document?.act_type, document?.document_type, 'Судебный документ');
  const documentText = firstText(
    text,
    document?.anonymized_text,
    document?.text,
    document?.content,
    document?.public_text,
    document?.full_text,
    document?.original_text,
  );
  const showRestoredWarning = Boolean(isRestored || restored);
  const metaRows = [
    ['Номер дела', info.case_number],
    ['Номер документа', info.document_number],
    ['Дата', info.document_date],
    ['Суд', info.court_name],
    ['Регион', info.region],
    ['Статья закона', info.legal_article],
    ['Судьи', join(info.judge_names)],
  ];

  return (
    <article className="court-document">
      {showRestoredWarning && (
        <div className="status-warning court-document-warning">
          Внимание: отображаются восстановленные данные. Доступ к просмотру должен фиксироваться в журнале аудита.
        </div>
      )}
      <header className="court-document-header">
        <h2 className="court-document-title">{documentTitle}</h2>
      </header>
      <dl className="court-document-meta">
        {metaRows.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{value || '—'}</dd>
          </div>
        ))}
      </dl>
      <div className="court-document-text">
        {documentText || 'Текст документа отсутствует. Возможно, документ ещё не был обезличен или опубликован.'}
      </div>
    </article>
  );
}
