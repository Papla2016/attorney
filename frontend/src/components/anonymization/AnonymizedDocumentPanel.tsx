import type { PendingMarker, RedactionEntity, ReviewMarker } from '../../api/types';
import CourtDocumentView from '../documents/CourtDocumentView';
import RichDocumentEditor from '../documents/RichDocumentEditor';

type Props = {
  mode: 'EDIT' | 'PREVIEW';
  onModeChange: (mode: 'EDIT' | 'PREVIEW') => void;
  anonymizedText: string;
  anonymizedContent: unknown;
  contentRevision: number;
  reviewMarkers: ReviewMarker[];
  pendingMarkers: PendingMarker[];
  redactionMarkers: RedactionEntity[];
  editorLocked?: boolean;
  onChange: (payload: { json: unknown; text: string }) => void;
  onRedactionClick: (entityId: string) => void;
  onPendingClick: (entityKey: string, surface: string) => void;
  onReviewClick: (clusterId: string, placeholder: string) => void;
};

export default function AnonymizedDocumentPanel({ mode, onModeChange, anonymizedText, anonymizedContent, contentRevision, reviewMarkers, pendingMarkers, redactionMarkers, editorLocked = false, onChange, onRedactionClick, onPendingClick, onReviewClick }: Props) {
  return <section className='anonymized-text-panel workspace-document-panel'>
    <div className='panel-header-row'>
      <div>
        <h2>Документ</h2>
        <p className='muted-text'>Редактируйте рабочую версию или проверьте итоговый вид с сохранением форматирования.</p>
      </div>
      <div className='anonymized-editor-tabs' role='tablist' aria-label='Режим просмотра документа'>
        <button type='button' className={`button ${mode === 'EDIT' ? 'entity-tab-active' : 'button-secondary'}`} onClick={() => onModeChange('EDIT')}>Редактирование</button>
        <button type='button' className={`button ${mode === 'PREVIEW' ? 'entity-tab-active' : 'button-secondary'}`} onClick={() => onModeChange('PREVIEW')}>Предпросмотр</button>
      </div>
    </div>
    {editorLocked && <p className='manual-decision-warning'>Документ временно недоступен для редактирования: выполняется операция с сущностями.</p>}
    {mode === 'EDIT' ? <RichDocumentEditor
      value={anonymizedContent || undefined}
      contentRevision={contentRevision}
      onChange={onChange}
      placeholder='Текст обезличенного документа'
      editable={!editorLocked}
      reviewMarkers={reviewMarkers}
      pendingMarkers={pendingMarkers}
      redactionMarkers={redactionMarkers.map((e) => ({ entity_id: e.entity_id, placeholder: e.placeholder || '', canonical_value: e.canonical_value, entity_class: e.entity_class, person_role: e.person_role, mentions_count: e.mentions_count || e.mentions?.length || 0 }))}
      showSensitiveTooltips
      onRedactionMarkerClick={onRedactionClick}
      onPendingMarkerClick={onPendingClick}
      onReviewMarkerClick={onReviewClick}
    /> : <CourtDocumentView text={anonymizedText} content={anonymizedContent} contentFormat='TIPTAP_JSON' variant='anonymizedPreview' />}
  </section>;
}
