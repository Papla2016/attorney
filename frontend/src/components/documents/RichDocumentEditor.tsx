import { EditorContent, useEditor } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import Underline from '@tiptap/extension-underline';
import TextAlign from '@tiptap/extension-text-align';
import Table from '@tiptap/extension-table';
import TableRow from '@tiptap/extension-table-row';
import TableHeader from '@tiptap/extension-table-header';
import TableCell from '@tiptap/extension-table-cell';
import Placeholder from '@tiptap/extension-placeholder';
import { useEffect, useRef } from 'react';
import { Extension } from '@tiptap/core';
import { Decoration, DecorationSet } from '@tiptap/pm/view';
import { Plugin, PluginKey } from '@tiptap/pm/state';
import type { PendingMarker, ReviewMarker } from '../../api/types';

export const REVIEW_MARKERS_META = 'updateReviewMarkers';
const reviewPluginKey = new PluginKey('reviewHighlight');

const ReviewHighlight = Extension.create<any>({
  name: 'reviewHighlight',
  addOptions: () => ({ onReviewClick: undefined, onPendingClick: undefined }),
  addProseMirrorPlugins() {
    const { onReviewClick, onPendingClick } = this.options as any;
    return [new Plugin({
      key: reviewPluginKey,
      state: {
        init: () => ({ reviewMarkers: [] as ReviewMarker[], pendingMarkers: [] as PendingMarker[] }),
        apply(tr, prev) { return tr.getMeta(REVIEW_MARKERS_META) || prev; },
      },
      props: {
        decorations: (state) => {
          const pluginState = reviewPluginKey.getState(state) || { reviewMarkers: [], pendingMarkers: [] };
          const dec: Decoration[] = [];
          pluginState.reviewMarkers.forEach((m: ReviewMarker) => {
            const text = m.placeholder || m.display_text; if (!text) return;
            state.doc.descendants((node, pos) => { if (!node.isText || !node.text) return; let idx=node.text.indexOf(text); while(idx>=0){ dec.push(Decoration.inline(pos+idx,pos+idx+text.length,{class:'review-highlight',title:'Значение уже обезличено, но требует подтверждения.','data-cluster-id':m.cluster_id||'','data-placeholder':text})); idx=node.text.indexOf(text,idx+text.length);} });
          });
          pluginState.pendingMarkers.forEach((m: PendingMarker) => {
            const text = m.surface_value; if (!text) return;
            state.doc.descendants((node, pos) => { if (!node.isText || !node.text) return; let idx=node.text.indexOf(text); while(idx>=0){ dec.push(Decoration.inline(pos+idx,pos+idx+text.length,{class:'pending-redaction-highlight',title:'В тексте обнаружены возможные персональные данные. Обработайте фрагмент перед публикацией.','data-entity-key':m.entity_key||'','data-surface':text})); idx=node.text.indexOf(text,idx+text.length);} });
          });
          return DecorationSet.create(state.doc, dec);
        },
        handleClick: (_v, _p, e) => { const t=e.target as HTMLElement; if(t?.classList?.contains('review-highlight')) onReviewClick?.(t.dataset.clusterId||'',t.dataset.placeholder||''); if(t?.classList?.contains('pending-redaction-highlight')) onPendingClick?.(t.dataset.entityKey||'',t.dataset.surface||''); return false; },
      },
    })];
  },
});

type Props = { value?: any; contentRevision?: number | string; onChange?: (payload: { json: any; text: string }) => void; placeholder?: string; editable?: boolean; onSelectionChange?: (text: string) => void; showToolbar?: boolean; reviewMarkers?: ReviewMarker[]; pendingMarkers?: PendingMarker[]; onReviewMarkerClick?: (clusterId: string, placeholder: string) => void; onPendingMarkerClick?: (entityKey: string, surfaceValue: string) => void; };

export default function RichDocumentEditor({ value, contentRevision, onChange, placeholder, editable = true, onSelectionChange, showToolbar = true, reviewMarkers = [], pendingMarkers = [], onReviewMarkerClick, onPendingMarkerClick }: Props) {
  const lastAppliedRevision = useRef<number | string | undefined>(undefined);
  const editor = useEditor({
    editable, shouldRerenderOnTransaction: false,
    extensions: [StarterKit.configure({ bulletList: { keepMarks: true }, orderedList: { keepMarks: true } }), Underline, TextAlign.configure({ types: ['heading', 'paragraph'] }), Table.configure({ resizable: true }), TableRow, TableHeader, TableCell, Placeholder.configure({ placeholder: placeholder || 'Введите текст документа...' }), ReviewHighlight.configure({ onReviewClick: onReviewMarkerClick, onPendingClick: onPendingMarkerClick })],
    content: value || '<p></p>', onUpdate: ({ editor: ed }) => onChange?.({ json: ed.getJSON(), text: ed.getText() }), onSelectionUpdate: ({ editor: ed }) => onSelectionChange?.(ed.state.doc.textBetween(ed.state.selection.from, ed.state.selection.to, ' ').trim()),
  });

  useEffect(() => { if (!editor) return; editor.view.dispatch(editor.state.tr.setMeta(REVIEW_MARKERS_META, { reviewMarkers, pendingMarkers })); }, [editor, reviewMarkers, pendingMarkers]);
  useEffect(() => { if (!editor || value === undefined) return; if (lastAppliedRevision.current === undefined) { lastAppliedRevision.current = contentRevision; return; } if (contentRevision !== undefined && contentRevision !== lastAppliedRevision.current) { editor.commands.setContent(value, false); lastAppliedRevision.current = contentRevision; } }, [contentRevision, editor, value]);
  if (!editor) return null;
  const btn = (label: string, title: string, action: () => void, active = false, disabled = false) => <button aria-label={title} type='button' title={title} disabled={disabled} className={`toolbar-button ${active ? 'toolbar-button-active' : ''}`} onClick={action}>{label}</button>;
  return <div className='rich-editor'>{showToolbar && <div className='rich-editor-toolbar'><div className='toolbar-group'><span className='toolbar-label'>Начертание</span>{btn('Ж','Жирный',()=>editor.chain().focus().toggleBold().run(),editor.isActive('bold'))}</div></div>}<div className='rich-editor-content'><EditorContent editor={editor} /></div></div>;
}
