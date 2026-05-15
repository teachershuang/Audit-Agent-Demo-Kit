import type { ReactNode } from "react";

export function AppShell({
  header,
  left,
  right,
  footer,
}: {
  header: ReactNode;
  left: ReactNode;
  right: ReactNode;
  footer: ReactNode;
}) {
  return (
    <div className="grid-line h-screen overflow-hidden px-5 py-5 text-slate-100 md:px-6 xl:px-8">
      <div className="mx-auto flex h-[calc(100vh-2.5rem)] w-full max-w-[1820px] flex-col gap-4 overflow-hidden">
        {header}
        <main className="grid min-h-0 flex-1 grid-cols-1 gap-4 overflow-hidden xl:grid-cols-[1.22fr_1fr]">
          <section className="min-h-0 overflow-hidden xl:min-h-[620px]">{left}</section>
          <section className="min-h-0 overflow-hidden xl:min-h-[620px]">{right}</section>
        </main>
        {footer}
      </div>
    </div>
  );
}
