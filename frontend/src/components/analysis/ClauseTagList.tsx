import type { ClauseTag } from "../../types/contract";
import { ClauseCard } from "./ClauseCard";

export function ClauseTagList({
  clauses,
  activeId,
  onSelect,
}: {
  clauses: ClauseTag[];
  activeId: string | null;
  onSelect: (clause: ClauseTag) => void;
}) {
  return (
    <div className="space-y-3">
      {clauses.map((clause) => (
        <ClauseCard key={clause.id} clause={clause} active={activeId === clause.id} onSelect={onSelect} />
      ))}
    </div>
  );
}
