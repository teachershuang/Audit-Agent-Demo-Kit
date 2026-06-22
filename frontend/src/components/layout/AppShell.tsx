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
  footer?: ReactNode;
}) {
  return (
    <div className="grid-line min-h-screen overflow-y-auto px-4 py-4 text-slate-100 md:px-6 xl:px-8">
      <div className="mx-auto flex min-h-[calc(100vh-2rem)] w-full max-w-[1820px] flex-col gap-4">
        {header}
        <main className="grid min-h-0 flex-1 grid-cols-1 gap-4 xl:h-[calc(100vh-20rem)] xl:min-h-[640px] xl:max-h-[760px] xl:grid-cols-[minmax(0,1.34fr)_minmax(460px,0.92fr)] xl:items-stretch xl:overflow-hidden">
          <section className="min-h-0 overflow-hidden">{left}</section>
          <section className="min-h-0 overflow-hidden">{right}</section>
        </main>
        {footer ? <div className="pt-1">{footer}</div> : null}
      </div>
    </div>
  );
}
