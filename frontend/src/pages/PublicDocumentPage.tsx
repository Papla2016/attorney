import { useParams } from 'react-router-dom'; import { useQuery } from '@tanstack/react-query'; import { getPublicDocument } from '../api/casesApi';
export default function PublicDocumentPage(){ const {documentId=''}=useParams(); const {data}=useQuery({queryKey:['doc',documentId],queryFn: async()=> (await getPublicDocument(documentId)).data});
 const copy=()=>navigator.clipboard.writeText(data?.anonymized_text||''); return <div><h2>{data?.title}</h2><pre>{data?.anonymized_text}</pre><button onClick={copy}>Скопировать текст</button></div>; }
