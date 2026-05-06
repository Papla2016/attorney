type CourtDocumentViewProps = {
  caseData?: any;
  document?: any;
  text?: string;
  restored?: boolean;
};

const join = (items?: string[]) => items?.filter(Boolean).join(', ') || '—';
const firstText = (...values: any[]) => values.find((v) => typeof v === 'string' && v.trim()) || '';

export default function CourtDocumentView({ caseData, document, text, restored }: CourtDocumentViewProps) {
  const judges = caseData?.judge_names || caseData?.judges || [];
  const participants = caseData?.participants || [];
  const documentText = firstText(text, document?.anonymized_text, document?.full_text, document?.text, document?.original_text);
  const title = document?.title || document?.act_type || 'Судебный акт';
  const court = caseData?.court_name || caseData?.court || document?.court || 'Суд не указан';

  return (
    <article className='court-document'>
      <header className='court-document-header'>
        <div className='court-document-material'>Материал № {caseData?.case_number || document?.case_number || '—'}</div>
        <h2 className='court-document-title'>{String(title).toUpperCase()}</h2>
        <p>{caseData?.document_date || document?.document_date || 'Дата не указана'}{caseData?.region ? `, ${caseData.region}` : ''}</p>
        <p>{court}</p>
      </header>
      <section className='court-document-section'>
        <p><b>Судья:</b> {join(judges)}</p>
        <p><b>Статья закона:</b> {caseData?.legal_article || caseData?.law_article || '—'}</p>
        {participants.length > 0 && <p><b>Участники:</b> {participants.map((p: any) => p.display_name || p.name || p.username || p.role).filter(Boolean).join(', ')}</p>}
      </section>
      <section className='court-document-section'>
        <h3>Установил</h3>
        <div className='court-document-text'>{documentText || 'Текст документа пока не загружен.'}</div>
      </section>
      <section className='court-document-section'>
        <h3>Постановил</h3>
        <div className='court-document-text'>{restored ? 'Восстановленный текст приведён выше. Персональные данные отображаются только пользователям с правом доступа.' : 'Обезличенная версия документа доступна для просмотра и публикации в соответствии со статусом обработки.'}</div>
      </section>
      <footer className='court-document-signature'>Судья {join(judges)}</footer>
    </article>
  );
}
