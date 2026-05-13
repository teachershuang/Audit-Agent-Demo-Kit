export function UploadPanel({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <div className="rounded-[28px] border border-dashed border-cyan-400/25 bg-cyan-400/[0.03] p-8 text-center">
      <h3 className="font-display text-2xl text-white">{title}</h3>
      <p className="mt-3 text-sm leading-7 text-slate-300">{description}</p>
    </div>
  );
}
