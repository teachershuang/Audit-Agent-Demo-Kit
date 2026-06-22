import type { ContractSection } from "../../types/contract";
import { ConfidenceBadge } from "../shared/ConfidenceBadge";

function buildTree(sections: ContractSection[]) {
  const sorted = [...sections].sort((left, right) => (left.sortOrder ?? 0) - (right.sortOrder ?? 0));
  const root: Array<{ section: ContractSection; children: any[] }> = [];
  const stack: Array<{ section: ContractSection; children: any[] }> = [];

  for (const section of sorted) {
    const node = { section, children: [] as Array<{ section: ContractSection; children: any[] }> };
    while (stack.length > 0 && (stack[stack.length - 1].section.level ?? 1) >= section.level) {
      stack.pop();
    }
    if (stack.length === 0) {
      root.push(node);
    } else {
      stack[stack.length - 1].children.push(node);
    }
    stack.push(node);
  }

  return root;
}

function SectionNode({
  node,
  activeId,
  depth,
  onSelect,
}: {
  node: { section: ContractSection; children: Array<{ section: ContractSection; children: any[] }> };
  activeId: string | null;
  depth: number;
  onSelect: (section: ContractSection) => void;
}) {
  const section = node.section;
  return (
    <div className="space-y-3">
      <button
        key={section.id}
        type="button"
        onClick={() => onSelect(section)}
        id={`card-${section.id}`}
        className={`w-full rounded-[22px] border p-4 text-left transition ${
          activeId === section.id
            ? "border-cyan-300/40 bg-cyan-400/[0.08]"
            : "border-white/8 bg-white/[0.03] hover:border-cyan-400/22"
        }`}
        style={{ marginLeft: `${Math.min(depth, 4) * 18}px` }}
      >
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-[11px] uppercase tracking-[0.22em] text-cyan-200/60">
              {section.sectionCode ?? `L${section.level}`} · 第 {section.page} 页
            </p>
            <h3 className="mt-1 text-base font-semibold text-white">{section.title}</h3>
          </div>
          <ConfidenceBadge value={section.confidence} />
        </div>
        <p className="mt-3 text-sm leading-7 text-slate-300">{section.summary}</p>
        <div className="mt-4 text-xs text-slate-400">{section.evidenceId ? "已建立证据定位" : "缺少证据定位"}</div>
      </button>
      {node.children.length > 0 ? (
        <div className="space-y-3 border-l border-cyan-400/12 pl-1">
          {node.children.map((child) => (
            <SectionNode key={child.section.id} node={child} activeId={activeId} depth={depth + 1} onSelect={onSelect} />
          ))}
        </div>
      ) : null}
    </div>
  );
}

export function SectionTree({
  sections,
  activeId,
  onSelect,
}: {
  sections: ContractSection[];
  activeId: string | null;
  onSelect: (section: ContractSection) => void;
}) {
  const tree = buildTree(sections);
  return (
    <div className="space-y-3">
      {tree.map((node) => (
        <SectionNode key={node.section.id} node={node} activeId={activeId} depth={0} onSelect={onSelect} />
      ))}
    </div>
  );
}
