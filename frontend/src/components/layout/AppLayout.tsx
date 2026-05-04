import type { ReactNode } from 'react';
import Header from './Header';

export default function AppLayout({ children }: { children: ReactNode }) {
  return (
    <>
      <Header />
      <main className="container page-content">{children}</main>
    </>
  );
}
