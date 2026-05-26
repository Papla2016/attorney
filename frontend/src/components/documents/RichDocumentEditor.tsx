import { EditorContent, useEditor } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import Underline from '@tiptap/extension-underline';
import TextAlign from '@tiptap/extension-text-align';
import Table from '@tiptap/extension-table';
import TableRow from '@tiptap/extension-table-row';
import TableHeader from '@tiptap/extension-table-header';
import TableCell from '@tiptap/extension-table-cell';
import Placeholder from '@tiptap/extension-placeholder';
import { useEffect, useMemo, useRef } from 'react';
import { Extension } from '@tiptap/core';
import { Decoration, DecorationSet } from '@tiptap/pm/view';
import { Plugin } from '@tiptap/pm/state';
import type { PendingMarker, ReviewMarker } from '../../api/types';

const ReviewHighlight = Extension.create<any>({
  name: 'reviewHighlight',
  addOptions: () => ({ reviewMarkers: [], pendingMarkers: [], onReviewClick: undefined, onPendingClick: undefined }),
  addProseMirrorPlugins() {
    const { reviewMarkers, pendingMarkers, onReviewClick, onPendingClick } = this.options;
    return [
      new Plugin({
        props: {
          decorations: (state) => {
            const dec: Decoration[] = [];
            reviewMarkers.forEach((m: ReviewMarker) => {
              const text = m.placeholder || m.display_text;
              if (!text) return;
              state.doc.descendants((node, pos) => {
                if (!node.isText || !node.text) return;
                let idx = node.text.indexOf(text);
                while (idx >= 0) {
                  dec.push(Decoration.inline(pos + idx, pos + idx + text.length, { class: 'review-highlight', title: `Обезличено, требуется подтверждение: ${m.reason || 'Уточните данные'}`, 'data-cluster-id': m.cluster_id || '', 'data-placeholder': text }));
                  idx = node.text.indexOf(text, idx + text.length);
                }
              });
            });
            pendingMarkers.forEach((m: PendingMarker) => {
              const text = m.surface_value;
              if (!text) return;
              state.doc.descendants((node, pos) => {
                if (!node.isText || !node.text) return;
                let idx = node.text.indexOf(text);
                while (idx >= 0) {
                  dec.push(Decoration.inline(pos + idx, pos + idx + text.length, { class: 'pending-redaction-highlight', title: `Найден новый фрагмент, который необходимо проверить перед публикацией: ${m.reason}`, 'data-entity-key': m.entity_key || '', 'data-surface': text }));
                  idx = node.text.indexOf(text, idx + text.length);
                }
              });
            });
            return DecorationSet.create(state.doc, dec);
          },
          handleClick: (_view, _pos, event) => {
            const target = event.target as HTMLElement;
            if (target?.classList?.contains('review-highlight')) onReviewClick?.(target.dataset.clusterId || '', target.dataset.placeholder || '');
            if (target?.classList?.contains('pending-redaction-highlight')) onPendingClick?.(target.dataset.entityKey || '', target.dataset.surface || '');
            return false;
          },
        },
      }),
    ];
  },
});

type Props = {
  value?: any;
  contentRevision?: number | string;
  onChange?: (payload: { json: any; text: string }) => void;
  placeholder?: string;
  editable?: boolean;
  onSelectionChange?: (text: string) => void;
  showToolbar?: boolean;
  reviewMarkers?: ReviewMarker[];
  pendingMarkers?: PendingMarker[];
  onReviewMarkerClick?: (clusterId: string, placeholder: string) => void;
  onPendingMarkerClick?: (entityKey: string, surfaceValue: string) => void;
};

export default function RichDocumentEditor({ value, contentRevision, onChange, placeholder, editable = true, onSelectionChange, showToolbar = true, reviewMarkers = [], pendingMarkers = [], onReviewMarkerClick, onPendingMarkerClick }: Props) {
  const lastAppliedRevision = useRef<number | string | undefined>(undefined);
  const markerKey = useMemo(() => JSON.stringify({ reviewMarkers, pendingMarkers }), [reviewMarkers, pendingMarkers]);
  const editor = useEditor({
    editable,
    shouldRerenderOnTransaction: false,
    extensions: [
      StarterKit.configure({ bulletList: { keepMarks: true }, orderedList: { keepMarks: true } }),
      Underline,
      TextAlign.configure({ types: ['heading', 'paragraph'] }),
      Table.configure({ resizable: true }), TableRow, TableHeader, TableCell,
      Placeholder.configure({ placeholder: placeholder || 'Введите текст документа...' }),
      ReviewHighlight.configure({ reviewMarkers, pendingMarkers, onReviewClick: onReviewMarkerClick, onPendingClick: onPendingMarkerClick, key: markerKey }),
    ],
    content: value || '<p></p>',
    onUpdate: ({ editor: ed }) => onChange?.({ json: ed.getJSON(), text: ed.getText() }),
    onSelectionUpdate: ({ editor: ed }) => onSelectionChange?.(ed.state.doc.textBetween(ed.state.selection.from, ed.state.selection.to, ' ').trim()),
  });

  useEffect(() => {
    if (!editor || value === undefined) return;
    if (lastAppliedRevision.current === undefined) {
      lastAppliedRevision.current = contentRevision;
      return;
    }
    const revisionChanged = contentRevision !== undefined && contentRevision !== lastAppliedRevision.current;
    if (!revisionChanged) return;
    editor.commands.setContent(value, false);
    lastAppliedRevision.current = contentRevision;
  }, [contentRevision, editor, value]);

  if (!editor) return null;
  const btn = (label: string, title: string, action: () => void, active = false, disabled = false) => (
    <button aria-label={title} type='button' title={title} disabled={disabled} className={`toolbar-button ${active ? 'toolbar-button-active' : ''}`} onClick={action}>{label}</button>
  );

  const headingLevel = editor.isActive('heading', { level: 2 }) ? 'h2' : editor.isActive('heading', { level: 3 }) ? 'h3' : 'p';

  return <div className='rich-editor'>
    {showToolbar && <div className='rich-editor-toolbar'>
      <div className='toolbar-group'><span className='toolbar-label'>Отмена</span>{btn('↶', 'Отменить', () => editor.chain().focus().undo().run(), false, !editor.can().undo())}{btn('↷', 'Повторить', () => editor.chain().focus().redo().run(), false, !editor.can().redo())}</div>
      <div className='toolbar-group'><span className='toolbar-label'>Начертание</span>{btn('Ж', 'Жирный', () => editor.chain().focus().toggleBold().run(), editor.isActive('bold'))}{btn('К', 'Курсив', () => editor.chain().focus().toggleItalic().run(), editor.isActive('italic'))}{btn('П', 'Подчёркнутый', () => editor.chain().focus().toggleUnderline().run(), editor.isActive('underline'))}{btn('З', 'Зачёркнутый', () => editor.chain().focus().toggleStrike().run(), editor.isActive('strike'))}</div>
      <div className='toolbar-group'><span className='toolbar-label'>Абзац</span><select aria-label='Тип абзаца' title='Тип абзаца' value={headingLevel} onChange={(e) => { const v = e.target.value; if (v === 'h2') editor.chain().focus().toggleHeading({ level: 2 }).run(); else if (v === 'h3') editor.chain().focus().toggleHeading({ level: 3 }).run(); else editor.chain().focus().setParagraph().run(); }}><option value='p'>Обычный текст</option><option value='h2'>Заголовок</option><option value='h3'>Подзаголовок</option></select>{btn('• Список', 'Маркированный список', () => editor.chain().focus().toggleBulletList().run(), editor.isActive('bulletList'))}{btn('1. Список', 'Нумерованный список', () => editor.chain().focus().toggleOrderedList().run(), editor.isActive('orderedList'))}{btn('❝', 'Цитата', () => editor.chain().focus().toggleBlockquote().run(), editor.isActive('blockquote'))}</div>
      <div className='toolbar-group'><span className='toolbar-label'>Выравнивание</span>{btn('Слева', 'По левому краю', () => editor.chain().focus().setTextAlign('left').run(), editor.isActive({ textAlign: 'left' }))}{btn('Центр', 'По центру', () => editor.chain().focus().setTextAlign('center').run(), editor.isActive({ textAlign: 'center' }))}{btn('Справа', 'По правому краю', () => editor.chain().focus().setTextAlign('right').run(), editor.isActive({ textAlign: 'right' }))}{btn('Ширина', 'По ширине', () => editor.chain().focus().setTextAlign('justify').run(), editor.isActive({ textAlign: 'justify' }))}</div>
      <div className='toolbar-group'><span className='toolbar-label'>Таблица</span>{btn('Вставить', 'Вставить таблицу', () => editor.chain().focus().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run())}{btn('Удалить', 'Удалить таблицу', () => editor.chain().focus().deleteTable().run())}{btn('+ Строка', 'Добавить строку', () => editor.chain().focus().addRowAfter().run())}{btn('+ Столбец', 'Добавить столбец', () => editor.chain().focus().addColumnAfter().run())}{btn('- Строка', 'Удалить строку', () => editor.chain().focus().deleteRow().run())}{btn('- Столбец', 'Удалить столбец', () => editor.chain().focus().deleteColumn().run())}</div>
      <div className='toolbar-group'><span className='toolbar-label'>Прочее</span>{btn('Линия', 'Горизонтальная линия', () => editor.chain().focus().setHorizontalRule().run())}{btn('Очистить', 'Очистить форматирование', () => editor.chain().focus().unsetAllMarks().clearNodes().run())}</div>
    </div>}
    <div className='rich-editor-content'><EditorContent editor={editor} /></div>
  </div>;
}
