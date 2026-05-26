import { EditorContent, useEditor } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import Underline from '@tiptap/extension-underline';
import TextAlign from '@tiptap/extension-text-align';
import Table from '@tiptap/extension-table';
import TableRow from '@tiptap/extension-table-row';
import TableHeader from '@tiptap/extension-table-header';
import TableCell from '@tiptap/extension-table-cell';
import Placeholder from '@tiptap/extension-placeholder';
import { useEffect } from 'react';
import { Extension } from '@tiptap/core';
import { Decoration, DecorationSet } from '@tiptap/pm/view';
import { Plugin } from '@tiptap/pm/state';

const ReviewHighlight = Extension.create<any>({
  name: 'reviewHighlight',
  addOptions: () => ({ markers: [], onClick: undefined }),
  addProseMirrorPlugins() {
    const { markers, onClick } = this.options;
    return [
      new Plugin({
        props: {
          decorations: (state) => {
            const dec: Decoration[] = [];
            markers.forEach((m: any) => {
              const text = m.placeholder || m.display_text;
              if (!text) return;
              state.doc.descendants((node, pos) => {
                if (!node.isText || !node.text) return;
                let idx = node.text.indexOf(text);
                while (idx >= 0) {
                  dec.push(Decoration.inline(pos + idx, pos + idx + text.length, { class: 'review-highlight', title: `Требуется проверка: ${m.reason || 'Уточните данные'}`, 'data-cluster-id': m.cluster_id || '', 'data-placeholder': text }));
                  idx = node.text.indexOf(text, idx + text.length);
                }
              });
            });
            return DecorationSet.create(state.doc, dec);
          },
          handleClick: (_view, _pos, event) => {
            const target = event.target as HTMLElement;
            if (target?.classList?.contains('review-highlight')) {
              onClick?.(target.dataset.clusterId || '', target.dataset.placeholder || '');
            }
            return false;
          },
        },
      }),
    ];
  },
});

type Props = { value?: any; onChange?: (payload: { json: any; text: string }) => void; placeholder?: string; editable?: boolean; onSelectionChange?: (text: string) => void; showToolbar?: boolean; reviewMarkers?: any[]; onReviewMarkerClick?: (clusterId: string, placeholder: string) => void };

export default function RichDocumentEditor({ value, onChange, placeholder, editable = true, onSelectionChange, showToolbar = true, reviewMarkers = [], onReviewMarkerClick }: Props) {
  const editor = useEditor({
    editable,
    extensions: [
      StarterKit.configure({ bulletList: { keepMarks: true }, orderedList: { keepMarks: true } }),
      Underline,
      TextAlign.configure({ types: ['heading', 'paragraph'] }),
      Table.configure({ resizable: true }), TableRow, TableHeader, TableCell,
      Placeholder.configure({ placeholder: placeholder || 'Введите текст документа...' }),
      ReviewHighlight.configure({ markers: reviewMarkers, onClick: onReviewMarkerClick }),
    ],
    content: value || '<p></p>',
    onUpdate: ({ editor: ed }) => onChange?.({ json: ed.getJSON(), text: ed.getText() }),
    onSelectionUpdate: ({ editor: ed }) => onSelectionChange?.(ed.state.doc.textBetween(ed.state.selection.from, ed.state.selection.to, ' ').trim()),
  });

  useEffect(() => {
    if (!editor || !value) return;
    const next = JSON.stringify(value);
    const current = JSON.stringify(editor.getJSON());
    if (next !== current) editor.commands.setContent(value, false);
  }, [value, editor]);
  if (!editor) return null;

  const btn = (label: string, title: string, action: () => void, active = false) => (
    <button type='button' title={title} className={`toolbar-button ${active ? 'toolbar-button-active' : ''}`} onClick={action}>{label}</button>
  );

  return <div className='rich-editor'>
    {showToolbar && <div className='rich-editor-toolbar'>
      <div className='toolbar-group'><span className='toolbar-label'>Отмена</span>{btn('↶', 'Отменить', () => editor.chain().focus().undo().run())}{btn('↷', 'Повторить', () => editor.chain().focus().redo().run())}</div>
      <div className='toolbar-group'><span className='toolbar-label'>Начертание</span>{btn('Ж', 'Жирный', () => editor.chain().focus().toggleBold().run(), editor.isActive('bold'))}{btn('К', 'Курсив', () => editor.chain().focus().toggleItalic().run(), editor.isActive('italic'))}{btn('Ч', 'Подчёркнутый', () => editor.chain().focus().toggleUnderline().run(), editor.isActive('underline'))}</div>
    </div>}
    <div className='rich-editor-content'><EditorContent editor={editor} /></div>
  </div>;
}
