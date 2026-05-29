export type TiptapNode = { type: string; content?: TiptapNode[]; text?: string; attrs?: Record<string, unknown>; marks?: unknown[] };

export function plainTextToTiptapDocument(text: string) {
  const normalized = (text || '').replace(/\r\n/g, '\n');
  const lines = normalized.split('\n');
  const content = lines.map((line) => {
    if (!line) return { type: 'paragraph' };
    return { type: 'paragraph', content: [{ type: 'text', text: line }] };
  });

  return { type: 'doc', content: content.length ? content : [{ type: 'paragraph' }] };
}

export function tiptapDocumentToPlainText(content: unknown): string {
  const textBlockTypes = new Set(['paragraph', 'heading']);

  const collectText = (node: any): string => {
    if (!node) return '';
    if (Array.isArray(node)) return node.map(collectText).join('');
    if (node.type === 'text' && typeof node.text === 'string') return node.text;
    if (Array.isArray(node.content)) return node.content.map(collectText).join('');
    return '';
  };

  const blocks: string[] = [];
  const walkBlocks = (node: any) => {
    if (!node) return;
    if (Array.isArray(node)) {
      node.forEach(walkBlocks);
      return;
    }
    if (textBlockTypes.has(node.type)) {
      blocks.push(collectText(node));
      return;
    }
    if (Array.isArray(node.content)) node.content.forEach(walkBlocks);
  };

  walkBlocks(content);
  return blocks.join('\n');
}
