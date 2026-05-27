import { EditorContent, useEditor } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import Underline from '@tiptap/extension-underline';
import TextAlign from '@tiptap/extension-text-align';
import Table from '@tiptap/extension-table';
import TableRow from '@tiptap/extension-table-row';
import TableHeader from '@tiptap/extension-table-header';
import TableCell from '@tiptap/extension-table-cell';
import Placeholder from '@tiptap/extension-placeholder';
import HorizontalRule from '@tiptap/extension-horizontal-rule';
import { useEffect, useRef } from 'react';
import { Extension } from '@tiptap/core';
import { Decoration, DecorationSet } from '@tiptap/pm/view';
import { Plugin, PluginKey } from '@tiptap/pm/state';
import type { PendingMarker, ReviewMarker } from '../../api/types';

export const UPDATE_REDACTION_MARKERS = 'updateRedactionMarkers';
const redactionPluginKey = new PluginKey('redactionHighlight');

type RedactionMarker = { entity_id: string; placeholder: string; canonical_value: string; entity_class: string; person_role?: string; mentions_count?: number };

const buildTooltip = (m: RedactionMarker) => {
  if (m.entity_class === 'PERSON' || m.entity_class === 'PERSON_FULL_NAME') {
    return `${m.placeholder} — ${m.canonical_value}. Роль: ${m.person_role || 'Не определено'}. Упоминаний: ${m.mentions_count || 0}.`;
  }
  return `${m.placeholder} — ${m.canonical_value}.`;
};

const ReviewHighlight = Extension.create<any>({
  name: 'reviewHighlight',
  addOptions: () => ({ onReviewClick: undefined, onPendingClick: undefined, onRedactionClick: undefined, showSensitiveTooltips: false }),
  addProseMirrorPlugins() {
    const { onReviewClick, onPendingClick, onRedactionClick, showSensitiveTooltips } = this.options as any;
    return [new Plugin({
      key: redactionPluginKey,
      state: {
        init: () => ({ redactionMarkers: [] as RedactionMarker[], reviewMarkers: [] as ReviewMarker[], pendingMarkers: [] as PendingMarker[] }),
        apply(tr, prev) { return tr.getMeta(UPDATE_REDACTION_MARKERS) || prev; },
      },
      props: {
        decorations: (state) => {
          const pluginState = redactionPluginKey.getState(state) || { redactionMarkers: [], reviewMarkers: [], pendingMarkers: [] };
          const dec: Decoration[] = [];
          pluginState.redactionMarkers.forEach((m: RedactionMarker) => {
            if (!m.placeholder) return;
            state.doc.descendants((node, pos) => {
              if (!node.isText || !node.text) return;
              let idx = node.text.indexOf(m.placeholder);
              while (idx >= 0) {
                dec.push(Decoration.inline(pos + idx, pos + idx + m.placeholder.length, { class: 'redaction-placeholder-highlight', title: showSensitiveTooltips ? buildTooltip(m) : m.placeholder, 'data-entity-id': m.entity_id }));
                idx = node.text.indexOf(m.placeholder, idx + m.placeholder.length);
              }
            });
          });
          pluginState.reviewMarkers.forEach((m: ReviewMarker) => {
            const text = m.placeholder || m.display_text; if (!text) return;
            state.doc.descendants((node, pos) => { if (!node.isText || !node.text) return; let idx = node.text.indexOf(text); while (idx >= 0) { dec.push(Decoration.inline(pos + idx, pos + idx + text.length, { class: 'review-highlight', title: 'Значение уже обезличено, но требует подтверждения.', 'data-cluster-id': m.cluster_id || '', 'data-placeholder': text })); idx = node.text.indexOf(text, idx + text.length); } });
          });
          pluginState.pendingMarkers.forEach((m: PendingMarker) => {
            const text = m.surface_value; if (!text) return;
            state.doc.descendants((node, pos) => { if (!node.isText || !node.text) return; let idx = node.text.indexOf(text); while (idx >= 0) { dec.push(Decoration.inline(pos + idx, pos + idx + text.length, { class: 'pending-redaction-highlight', title: 'В тексте обнаружены возможные персональные данные.', 'data-entity-key': m.entity_key || '', 'data-surface': text })); idx = node.text.indexOf(text, idx + text.length); } });
          });
          return DecorationSet.create(state.doc, dec);
        },
        handleClick: (_v, _p, e) => {
          const t = e.target as HTMLElement;
          if (t?.classList?.contains('redaction-placeholder-highlight')) onRedactionClick?.(t.dataset.entityId || '');
          if (t?.classList?.contains('review-highlight')) onReviewClick?.(t.dataset.clusterId || '', t.dataset.placeholder || '');
          if (t?.classList?.contains('pending-redaction-highlight')) onPendingClick?.(t.dataset.entityKey || '', t.dataset.surface || '');
          return false;
        },
      },
    })];
  },
});

type Props = { value?: any; contentRevision?: number | string; onChange?: (payload: { json: any; text: string }) => void; placeholder?: string; editable?: boolean; onSelectionChange?: (text: string) => void; showToolbar?: boolean; reviewMarkers?: ReviewMarker[]; pendingMarkers?: PendingMarker[]; redactionMarkers?: RedactionMarker[]; showSensitiveTooltips?: boolean; onReviewMarkerClick?: (clusterId: string, placeholder: string) => void; onPendingMarkerClick?: (entityKey: string, surfaceValue: string) => void; onRedactionMarkerClick?: (entityId: string) => void; };

export default function RichDocumentEditor({ value, contentRevision, onChange, placeholder, editable = true, onSelectionChange, showToolbar = true, reviewMarkers = [], pendingMarkers = [], redactionMarkers = [], showSensitiveTooltips = false, onReviewMarkerClick, onPendingMarkerClick, onRedactionMarkerClick }: Props) {
  const lastAppliedRevision = useRef<number | string | undefined>(undefined);
  const editor = useEditor({
    editable, shouldRerenderOnTransaction: false,
    extensions: [StarterKit.configure({ bulletList: { keepMarks: true }, orderedList: { keepMarks: true } }), Underline, HorizontalRule, TextAlign.configure({ types: ['heading', 'paragraph'] }), Table.configure({ resizable: true }), TableRow, TableHeader, TableCell, Placeholder.configure({ placeholder: placeholder || 'Введите текст документа...' }), ReviewHighlight.configure({ onReviewClick: onReviewMarkerClick, onPendingClick: onPendingMarkerClick, onRedactionClick: onRedactionMarkerClick, showSensitiveTooltips })],
    content: value || '<p></p>', onUpdate: ({ editor: ed }) => onChange?.({ json: ed.getJSON(), text: ed.getText() }), onSelectionUpdate: ({ editor: ed }) => onSelectionChange?.(ed.state.doc.textBetween(ed.state.selection.from, ed.state.selection.to, ' ').trim()),
  });

  useEffect(() => { if (!editor) return; editor.view.dispatch(editor.state.tr.setMeta(UPDATE_REDACTION_MARKERS, { redactionMarkers, reviewMarkers, pendingMarkers })); }, [editor, redactionMarkers, reviewMarkers, pendingMarkers]);
  useEffect(() => { if (!editor || value === undefined) return; if (lastAppliedRevision.current === undefined) { lastAppliedRevision.current = contentRevision; return; } if (contentRevision !== undefined && contentRevision !== lastAppliedRevision.current) { editor.commands.setContent(value, false); lastAppliedRevision.current = contentRevision; } }, [contentRevision, editor, value]);
  if (!editor) return null;
  const btn = (label: string, title: string, action: () => void, active = false, disabled = false) => <button aria-label={title} type='button' title={title} disabled={disabled} className={`toolbar-button ${active ? 'toolbar-button-active' : ''}`} onClick={action}>{label}</button>;
  return <div className='rich-editor'>{showToolbar && <div className='rich-editor-toolbar'>
    <div className='toolbar-group'>{btn('↶', 'Отменить', () => editor.chain().focus().undo().run(), false, !editor.can().undo())}{btn('↷', 'Повторить', () => editor.chain().focus().redo().run(), false, !editor.can().redo())}</div>
    <div className='toolbar-group'>{btn('Ж', 'Жирный', () => editor.chain().focus().toggleBold().run(), editor.isActive('bold'))}{btn('К', 'Курсив', () => editor.chain().focus().toggleItalic().run(), editor.isActive('italic'))}{btn('Ч', 'Подчёркнутый', () => editor.chain().focus().toggleUnderline().run(), editor.isActive('underline'))}{btn('S', 'Зачёркнутый', () => editor.chain().focus().toggleStrike().run(), editor.isActive('strike'))}</div>
    <div className='toolbar-group'>{btn('Т', 'Обычный текст', () => editor.chain().focus().setParagraph().run(), editor.isActive('paragraph'))}{btn('H1', 'Заголовок', () => editor.chain().focus().toggleHeading({ level: 2 }).run(), editor.isActive('heading', { level: 2 }))}{btn('H2', 'Подзаголовок', () => editor.chain().focus().toggleHeading({ level: 3 }).run(), editor.isActive('heading', { level: 3 }))}{btn('•', 'Маркированный список', () => editor.chain().focus().toggleBulletList().run(), editor.isActive('bulletList'))}{btn('1.', 'Нумерованный список', () => editor.chain().focus().toggleOrderedList().run(), editor.isActive('orderedList'))}{btn('❝', 'Цитата', () => editor.chain().focus().toggleBlockquote().run(), editor.isActive('blockquote'))}</div>
    <div className='toolbar-group'>{btn('⟸', 'По левому краю', () => editor.chain().focus().setTextAlign('left').run(), editor.isActive({ textAlign: 'left' }))}{btn('≡', 'По центру', () => editor.chain().focus().setTextAlign('center').run(), editor.isActive({ textAlign: 'center' }))}{btn('⟹', 'По правому краю', () => editor.chain().focus().setTextAlign('right').run(), editor.isActive({ textAlign: 'right' }))}{btn('☰', 'По ширине', () => editor.chain().focus().setTextAlign('justify').run(), editor.isActive({ textAlign: 'justify' }))}</div>
    <div className='toolbar-group'>{btn('⊞', 'Вставить таблицу', () => editor.chain().focus().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run())}{btn('⌫⊞', 'Удалить таблицу', () => editor.chain().focus().deleteTable().run())}{btn('+Стр', 'Добавить строку', () => editor.chain().focus().addRowAfter().run())}{btn('+Стлб', 'Добавить столбец', () => editor.chain().focus().addColumnAfter().run())}{btn('-Стр', 'Удалить строку', () => editor.chain().focus().deleteRow().run())}{btn('-Стлб', 'Удалить столбец', () => editor.chain().focus().deleteColumn().run())}</div>
    <div className='toolbar-group'>{btn('—', 'Горизонтальная линия', () => editor.chain().focus().setHorizontalRule().run())}{btn('Tx', 'Очистить форматирование', () => editor.chain().focus().clearNodes().unsetAllMarks().run())}</div>
  </div>}<div className='rich-editor-content'><EditorContent editor={editor} /></div></div>;
}
