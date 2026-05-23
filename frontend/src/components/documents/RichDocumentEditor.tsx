import { EditorContent, useEditor } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import Underline from '@tiptap/extension-underline';
import TextAlign from '@tiptap/extension-text-align';
import Highlight from '@tiptap/extension-highlight';
import Table from '@tiptap/extension-table';
import TableRow from '@tiptap/extension-table-row';
import TableHeader from '@tiptap/extension-table-header';
import TableCell from '@tiptap/extension-table-cell';
import Placeholder from '@tiptap/extension-placeholder';
import { useEffect } from 'react';

type Props = { value?: any; onChange?: (payload: { json: any; text: string }) => void; placeholder?: string; editable?: boolean; onSelectionChange?: (text: string) => void };

export default function RichDocumentEditor({ value, onChange, placeholder, editable = true, onSelectionChange }: Props) {
  const editor = useEditor({
    editable,
    extensions: [StarterKit, Underline, Highlight, TextAlign.configure({ types: ['heading', 'paragraph'] }), Table.configure({ resizable: true }), TableRow, TableHeader, TableCell, Placeholder.configure({ placeholder: placeholder || 'Введите текст документа...' })],
    content: value || '<p></p>',
    onUpdate: ({ editor: ed }) => onChange?.({ json: ed.getJSON(), text: ed.getText() }),
    onSelectionUpdate: ({ editor: ed }) => onSelectionChange?.(ed.state.doc.textBetween(ed.state.selection.from, ed.state.selection.to, ' ').trim())
  });
  useEffect(() => { if (editor && value) editor.commands.setContent(value, false); }, [value]);
  if (!editor) return null;
  const b = (label: string, action: () => void) => <button type='button' className='button button-secondary' onClick={action}>{label}</button>;
  return <div className='rich-editor'><div className='rich-editor-toolbar'>
    {b('↶', () => editor.chain().focus().undo().run())}{b('↷', () => editor.chain().focus().redo().run())}
    {b('B', () => editor.chain().focus().toggleBold().run())}{b('I', () => editor.chain().focus().toggleItalic().run())}{b('U', () => editor.chain().focus().toggleUnderline().run())}
    {b('S', () => editor.chain().focus().toggleStrike().run())}{b('H2', () => editor.chain().focus().toggleHeading({ level: 2 }).run())}{b('P', () => editor.chain().focus().setParagraph().run())}
    {b('• List', () => editor.chain().focus().toggleBulletList().run())}{b('1. List', () => editor.chain().focus().toggleOrderedList().run())}{b('Quote', () => editor.chain().focus().toggleBlockquote().run())}
    {b('Left', () => editor.chain().focus().setTextAlign('left').run())}{b('Center', () => editor.chain().focus().setTextAlign('center').run())}{b('Right', () => editor.chain().focus().setTextAlign('right').run())}{b('Justify', () => editor.chain().focus().setTextAlign('justify').run())}
    {b('Table+', () => editor.chain().focus().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run())}{b('Table-', () => editor.chain().focus().deleteTable().run())}
    {b('HR', () => editor.chain().focus().setHorizontalRule().run())}{b('Clear', () => editor.chain().focus().unsetAllMarks().clearNodes().run())}
  </div><div className='rich-editor-content'><EditorContent editor={editor} /></div></div>;
}
