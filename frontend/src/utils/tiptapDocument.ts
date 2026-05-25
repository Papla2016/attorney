export type TiptapNode = { type: string; content?: TiptapNode[]; text?: string };

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
  const walk = (node: any): string[] => {
    if (!node) return [];
    if (Array.isArray(node)) return node.flatMap(walk);
    if (node.type === 'text' && typeof node.text === 'string') return [node.text];
    if (node.type === 'paragraph') {
      const paragraphText = walk(node.content).join('');
      return [paragraphText];
    }
    return walk(node.content);
  };

  return walk((content as any)?.content ?? content).join('\n');
}
