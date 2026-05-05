import { useMemo, useState } from 'react';

export default function AutocompleteInput({ value, onChange, options, placeholder, name }: { value: string; onChange: (value: string) => void; options: string[]; placeholder?: string; name?: string; }) {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const filtered = useMemo(() => options.filter((opt) => opt.toLowerCase().includes(value.toLowerCase())).slice(0, 8), [options, value]);
  return <div className='autocomplete'>
    <input name={name} value={value} placeholder={placeholder} onChange={(e) => { onChange(e.target.value); setOpen(true); }} onFocus={() => setOpen(true)} onKeyDown={(e) => {
      if (!open && e.key === 'ArrowDown') setOpen(true);
      if (e.key === 'ArrowDown') { e.preventDefault(); setActive((x) => Math.min(x + 1, filtered.length - 1)); }
      if (e.key === 'ArrowUp') { e.preventDefault(); setActive((x) => Math.max(x - 1, 0)); }
      if (e.key === 'Enter' && open && filtered[active]) { e.preventDefault(); onChange(filtered[active]); setOpen(false); }
      if (e.key === 'Escape') setOpen(false);
    }} />
    {open && filtered.length > 0 && <ul className='autocomplete-list'>{filtered.map((opt, idx) => <li key={opt} className={idx === active ? 'active' : ''} onMouseDown={() => { onChange(opt); setOpen(false); }}>{opt}</li>)}</ul>}
  </div>;
}
