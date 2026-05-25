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

type Props = { value?: any; onChange?: (payload: { json: any; text: string }) => void; placeholder?: string; editable?: boolean; onSelectionChange?: (text: string) => void };

export default function RichDocumentEditor({ value, onChange, placeholder, editable = true, onSelectionChange }: Props) {
  const editor = useEditor({
    editable,
    extensions: [
      StarterKit.configure({ bulletList: { keepMarks: true }, orderedList: { keepMarks: true } }),
      Underline,
      TextAlign.configure({ types: ['heading', 'paragraph'] }),
      Table.configure({ resizable: true }), TableRow, TableHeader, TableCell,
      Placeholder.configure({ placeholder: placeholder || 'Введите текст документа...' })
    ],
    content: value || '<p></p>',
    onUpdate: ({ editor: ed }) => onChange?.({ json: ed.getJSON(), text: ed.getText() }),
    onSelectionUpdate: ({ editor: ed }) => onSelectionChange?.(ed.state.doc.textBetween(ed.state.selection.from, ed.state.selection.to, ' ').trim())
  });

  useEffect(() => { if (editor && value) editor.commands.setContent(value, false); }, [value, editor]);
  if (!editor) return null;

  const btn = (label: string, title: string, action: () => void, active = false) => (
    <button type='button' title={title} className={`toolbar-button ${active ? 'toolbar-button-active' : ''}`} onClick={action}>{label}</button>
  );

  return <div className='rich-editor'>
    <div className='rich-editor-toolbar'>
      <div className='toolbar-group'><span className='toolbar-label'>Отмена</span>
        {btn('↶', 'Отменить', () => editor.chain().focus().undo().run())}
        {btn('↷', 'Повторить', () => editor.chain().focus().redo().run())}
      </div>
      <div className='toolbar-group'><span className='toolbar-label'>Начертание</span>
        {btn('Ж', 'Жирный', () => editor.chain().focus().toggleBold().run(), editor.isActive('bold'))}
        {btn('К', 'Курсив', () => editor.chain().focus().toggleItalic().run(), editor.isActive('italic'))}
        {btn('Ч', 'Подчёркнутый', () => editor.chain().focus().toggleUnderline().run(), editor.isActive('underline'))}
        {btn('З', 'Зачёркнутый', () => editor.chain().focus().toggleStrike().run(), editor.isActive('strike'))}
      </div>
      <div className='toolbar-group'><span className='toolbar-label'>Абзац</span>
        <select value={editor.isActive('heading', { level: 2 }) ? 'h2' : editor.isActive('heading', { level: 3 }) ? 'h3' : 'p'} onChange={(e)=>{const v=e.target.value; const c=editor.chain().focus(); if(v==='h2') c.toggleHeading({level:2}).run(); else if(v==='h3') c.toggleHeading({level:3}).run(); else c.setParagraph().run();}}>
          <option value='p'>Обычный текст</option><option value='h2'>Заголовок</option><option value='h3'>Подзаголовок</option>
        </select>
        {btn('•', 'Маркированный список', () => editor.chain().focus().toggleBulletList().run(), editor.isActive('bulletList'))}
        {btn('1.', 'Нумерованный список', () => editor.chain().focus().toggleOrderedList().run(), editor.isActive('orderedList'))}
        {btn('❝', 'Цитата', () => editor.chain().focus().toggleBlockquote().run(), editor.isActive('blockquote'))}
      </div>
      <div className='toolbar-group'><span className='toolbar-label'>Выравнивание</span>
        {btn('⇤', 'По левому краю', () => editor.chain().focus().setTextAlign('left').run(), editor.isActive({ textAlign: 'left' }))}
        {btn('≡', 'По центру', () => editor.chain().focus().setTextAlign('center').run(), editor.isActive({ textAlign: 'center' }))}
        {btn('⇥', 'По правому краю', () => editor.chain().focus().setTextAlign('right').run(), editor.isActive({ textAlign: 'right' }))}
        {btn('☰', 'По ширине', () => editor.chain().focus().setTextAlign('justify').run(), editor.isActive({ textAlign: 'justify' }))}
      </div>
      <div className='toolbar-group'><span className='toolbar-label'>Таблица</span>
        {btn('+Табл', 'Вставить таблицу', () => editor.chain().focus().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run())}
        {btn('-Табл', 'Удалить таблицу', () => editor.chain().focus().deleteTable().run())}
      </div>
      <div className='toolbar-group'><span className='toolbar-label'>Прочее</span>
        {btn('—', 'Горизонтальная линия', () => editor.chain().focus().setHorizontalRule().run())}
        {btn('Очистить', 'Очистить форматирование', () => editor.chain().focus().unsetAllMarks().clearNodes().run())}
      </div>
    </div>
    <div className='rich-editor-content'><EditorContent editor={editor} /></div>
  </div>;
}
